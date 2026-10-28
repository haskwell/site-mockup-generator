import argparse
import json
import os
import random
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from PIL import Image, ImageOps
from playwright.sync_api import Page, sync_playwright
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from logging_config import get_logger
except ModuleNotFoundError:
    from src.logging_config import get_logger

try:
    from pipeline_common import launch_browser
except ModuleNotFoundError:
    from src.pipeline_common import launch_browser

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = get_logger("scraper")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
WEB_MAX_SIDE = 1200  # longest side of the web-sized copy, in px


# --------------------------------------------------------------------------
# Image downloading / validation
# --------------------------------------------------------------------------
def is_valid_image(path: str, min_side: int = 200) -> bool:
    """True if the file opens as an image and isn't a tiny icon/placeholder."""
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            return min(im.size) >= min_side
    except Exception:
        return False


def download_image(session: requests.Session, url: str, dest: str) -> bool:
    """Download to a .part file, validate, then move into place."""
    tmp = dest + ".part"
    try:
        with session.get(url, stream=True, timeout=20) as r:
            if r.status_code != 200:
                logger.warning(
                    "Failed to download %s (status %d)", url[:80], r.status_code
                )
                return False
            if not r.headers.get("Content-Type", "").startswith("image/"):
                logger.warning("Not an image response for %s", url[:80])
                return False
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        min_side = 100 if dest.endswith("pfp.jpg") else 200  # profile pics are small
        if not is_valid_image(tmp, min_side):
            logger.warning("Rejected corrupt/tiny image from %s", url[:80])
            os.remove(tmp)
            return False
        os.replace(tmp, dest)
        return True
    except Exception as e:
        logger.warning("Error downloading %s: %s", url[:80], e)
        if os.path.exists(tmp):
            os.remove(tmp)
        return False


def download_images_concurrently(
    tasks: List[Tuple[str, str]], max_workers: int = 8
) -> Set[str]:
    """Download many images; returns the set of destination paths that succeeded."""
    ok: Set[str] = set()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    with requests.Session() as session:
        session.headers.update({"User-Agent": USER_AGENT})
        session.mount("https://", HTTPAdapter(max_retries=retry))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(download_image, session, url, path): path
                for url, path in tasks
            }
            for future in as_completed(futures):
                path = futures[future]
                try:
                    if future.result():
                        ok.add(path)
                        logger.info("Downloaded: %s", os.path.basename(path))
                except Exception as exc:
                    logger.error("Download exception for %s: %s", path, exc)
    return ok


def make_web_copy(src: str, dest: str) -> Tuple[int, int]:
    """Create a web-sized WebP copy. Returns (width, height) of the copy."""
    with Image.open(src) as im:
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in getattr(im, "info", {})):
            alpha = im.convert("RGBA")
            bg = Image.new("RGBA", alpha.size, (255, 255, 255, 255))
            im = Image.alpha_composite(bg, alpha).convert("RGB")
        else:
            im = im.convert("RGB")
        im.thumbnail((WEB_MAX_SIDE, WEB_MAX_SIDE))
        im.save(dest, "WEBP", quality=82)
        return im.size


# --------------------------------------------------------------------------
# Page helpers
# --------------------------------------------------------------------------
def dismiss_instagram_modals(page: Page) -> None:
    """Dismiss cookie consent prompts, login dialogs, or notifications."""
    button_candidates = [
        {"name": "Allow all cookies", "exact": False},
        {"name": "Decline optional cookies", "exact": False},
        {"name": "Allow essential and optional cookies", "exact": False},
        {"name": "Only allow essential cookies", "exact": False},
        {"name": "Close", "exact": True},
        {"name": "Not Now", "exact": True},
        {"name": "Not now", "exact": True},
        {"name": "Cancel", "exact": True},
    ]
    for btn in button_candidates:
        try:
            locator = page.get_by_role("button", name=btn["name"], exact=btn["exact"])
            if locator.count() > 0 and locator.first.is_visible():
                locator.first.click(timeout=2000)
                logger.info("Dismissed modal via '%s' button.", btn["name"])
                page.wait_for_timeout(600)
                return
        except Exception:
            pass

    try:
        close_icon = page.locator('svg[aria-label="Close"], [aria-label="Close"]').first
        if close_icon.count() > 0 and close_icon.is_visible():
            close_icon.click(timeout=1500)
            logger.info("Dismissed modal via aria-label='Close'.")
            page.wait_for_timeout(600)
    except Exception:
        pass


def click_show_more_posts(page: Page, username: str) -> bool:
    """Click 'Show more posts' if present, to trigger the next batch."""
    for name_text in (f"Show more posts from {username}", "Show more posts"):
        for locator in (
            page.get_by_role("button", name=name_text, exact=False),
            page.locator(f'[role="button"]:has-text("{name_text}")'),
        ):
            try:
                if locator.count() > 0 and locator.first.is_visible():
                    locator.first.scroll_into_view_if_needed(timeout=3000)
                    locator.first.click(timeout=3000)
                    logger.info("Clicked 'Show more posts'.")
                    page.wait_for_timeout(1500)
                    return True
            except Exception:
                pass
    return False


def is_login_wall(page: Page) -> bool:
    return "accounts/login" in page.url


POST_LINKS = 'a[href*="/p/"], a[href*="/reel/"]'


def load_posts(page: Page, username: str, max_posts: int, max_rounds: int = 25) -> None:
    """Scroll until we have enough posts or the count stops growing."""
    last, stagnant = -1, 0
    for _ in range(max_rounds):
        count = page.locator(POST_LINKS).count()
        if count >= max_posts:
            break
        stagnant = stagnant + 1 if count == last else 0
        if stagnant >= 3:
            break
        last = count
        page.mouse.wheel(0, 1200)
        page.wait_for_timeout(random.randint(700, 1300))
        dismiss_instagram_modals(page)
        click_show_more_posts(page, username)
    logger.info(
        "Post links visible after scrolling: %d", page.locator(POST_LINKS).count()
    )


def collect_posts(page: Page, max_posts: int) -> List[Dict[str, Any]]:
    """Read post links and pick the largest image from each srcset."""
    return page.evaluate(
        r"""(maxPosts) => {
            const out = [], seen = new Set();
            for (const a of document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]')) {
                const img = a.querySelector('img');
                const m = (a.getAttribute('href') || '').match(/\/(p|reel)\/([^\/?]+)/);
                if (!img || !m || seen.has(m[2])) continue;
                seen.add(m[2]);
                let best = img.src || '', bestW = 0;
                for (const part of (img.srcset || '').split(',')) {
                    const [u, w] = part.trim().split(/\s+/);
                    const width = parseInt(w) || 0;
                    if (u && width > bestW) { best = u; bestW = width; }
                }
                if (!best.startsWith('https://')) continue;
                out.push({
                    shortcode: m[2], kind: m[1], src: best,
                    source_width: bestW, alt: (img.alt || '').trim()
                });
                if (out.length >= maxPosts) break;
            }
            return out;
        }""",
        max_posts,
    )


def parse_og_description(desc: str) -> Dict[str, str]:
    """
    Best-effort parse of a post's og:description, which usually looks like:
      '1,234 likes, 56 comments - handle on October 1, 2025: "caption".'
    The format can change, so we keep the raw string as a fallback.
    """
    # The caption part is optional: posts without a caption still yield date + stats.
    m = re.match(
        r"^(?P<stats>.*?) - (?P<who>.*?) on "
        r"(?P<date>[A-Z][a-z]+ \d{1,2}, \d{4})"
        r'(?:: [\u201c"](?P<cap>.*)[\u201d"])?\.?\s*$',
        desc,
        re.DOTALL,
    )
    if m:
        return {
            "caption": (m["cap"] or "").strip(),
            "date": m["date"].strip(),
            "stats_raw": m["stats"].strip(),
            "raw_meta": desc,
        }
    return {"caption": "", "date": "", "stats_raw": "", "raw_meta": desc}


def date_from_alt(alt: str) -> str:
    """Fallback: alt text often contains 'on September 30, 2026'."""
    m = re.search(r"on ([A-Z][a-z]+ \d{1,2}, \d{4})", alt)
    return m.group(1) if m else ""


def fetch_post_meta(
    page: Page, shortcode: str, kind: str, label: str = ""
) -> Optional[Dict[str, str]]:
    """Open a single post page and read its meta description. None if login wall."""
    path = "reel" if kind == "reel" else "p"
    post_url = f"https://www.instagram.com/{path}/{shortcode}/"
    logger.info(
        "%sOpening %s: %s", label, "reel" if kind == "reel" else "post", post_url
    )
    try:
        page.goto(post_url, timeout=30000)
    except Exception as e:
        logger.warning("%sNavigation warning for %s: %s", label, shortcode, e)
        if shortcode not in (page.url or ""):
            return None
    dismiss_instagram_modals(page)
    if is_login_wall(page):
        logger.warning("%sRedirected to login wall: %s", label, page.url)
        return None
    desc = page.evaluate(
        """() => ({
            description: document.querySelector('meta[property="og:description"]')?.content || '',
            image: document.querySelector('meta[property="og:image"]')?.content || ''
        })"""
    )
    result = parse_og_description(desc.get("description", ""))
    result["image"] = desc.get("image", "")
    return result


# --------------------------------------------------------------------------
# Main scrape
# --------------------------------------------------------------------------
def scrape_profile(
    username: str,
    max_posts: int = 18,
    fetch_captions: bool = False,
    auth_path: str = "",
    force: bool = False,
    headed: bool = False,
) -> Dict[str, Any]:
    url = f"https://www.instagram.com/{username}/"
    output_dir = f"{username}_data"
    staging = output_dir + ".tmp"
    json_final = os.path.join(output_dir, "profile_data.json")

    # Skip only if a previous run actually produced usable data.
    if os.path.exists(json_final) and not force:
        with open(json_final, encoding="utf-8") as f:
            existing = json.load(f)
        if existing.get("posts"):
            logger.info("Already scraped (use --force to redo): %s", json_final)
            return existing
        logger.info("Existing data has no posts; scraping again.")

    # Build in a staging folder so a failed run never leaves a half-made folder.
    if os.path.exists(staging):
        shutil.rmtree(staging)
    os.makedirs(os.path.join(staging, "posts", "orig"))
    os.makedirs(os.path.join(staging, "posts", "web"))
    os.makedirs("debug", exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = launch_browser(p, headless=not headed)
            ctx_kwargs: Dict[str, Any] = {
                "user_agent": USER_AGENT,
                "viewport": {"width": 1280, "height": 800},
                "locale": "en-US",
                "extra_http_headers": {"Accept-Language": "en-US,en;q=0.9"},
            }
            if auth_path and os.path.exists(auth_path):
                ctx_kwargs["storage_state"] = auth_path
                logger.info("Using saved login session: %s", auth_path)
            context = browser.new_context(**ctx_kwargs)
            page = context.new_page()

            logger.info("Loading profile for @%s...", username)
            try:
                page.goto(url, timeout=45000)
            except Exception as e:
                logger.warning("Initial navigation warning: %s. Continuing...", e)

            dismiss_instagram_modals(page)
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except Exception:
                pass
            dismiss_instagram_modals(page)

            login_wall = is_login_wall(page)
            if login_wall:
                raise RuntimeError("LOGIN_WALL: redirected to Instagram login; stopping retries to avoid repeated requests")
            page_text = page.locator("body").inner_text(timeout=5000).casefold()
            if "this account is private" in page_text or "account is private" in page_text:
                raise RuntimeError("PRIVATE_ACCOUNT: Instagram reports this profile is private")
            if "sorry, this page isn't available" in page_text or "page may have been removed" in page_text:
                raise RuntimeError("ACCOUNT_UNAVAILABLE: Instagram says this profile is unavailable")

            meta = page.evaluate("""() => ({
                ogImage: document.querySelector('meta[property="og:image"]')?.content || "",
                ogTitle: document.querySelector('meta[property="og:title"]')?.content || "",
                ogDesc: document.querySelector('meta[name="description"]')?.content || ""
            })""")
            pfp_url = meta.get("ogImage", "")
            og_title = meta.get("ogTitle", "")
            og_desc = meta.get("ogDesc", "")
            name = og_title.split(" (@")[0] if og_title else username

            bio = ""
            if 'on Instagram: "' in og_desc:
                bio = og_desc.split('on Instagram: "')[-1].strip('"')

            def stat(label: str) -> str:
                m = re.search(r"([\d.,]+[KMkm]?)\s+" + label, og_desc)
                return m.group(1) if m else ""

            load_posts(page, username, max_posts)
            page.screenshot(path=os.path.join("debug", f"{username}.png"))
            items = collect_posts(page, max_posts)
            logger.info("Collected %d post(s).", len(items))

            # Optional: real captions + dates from each post page.
            captions_completed = False
            if fetch_captions and items:
                total = len(items)
                logger.info(
                    "Fetching captions: opening %d post page(s) one by one...", total
                )
                post_page = context.new_page()
                for n, item in enumerate(items, 1):
                    label = f"[{n}/{total}] "
                    result = fetch_post_meta(
                        post_page, item["shortcode"], item["kind"], label
                    )
                    if result is None:
                        logger.warning(
                            "Hit login wall fetching captions; stopping early (%d/%d done).",
                            n - 1,
                            total,
                        )
                        break
                    item.update(result)
                    if result.get("image", "").startswith("https://"):
                        item["src"] = result["image"]
                    cap = result.get("caption", "")
                    logger.info(
                        "%sGot date=%s, stats=%s, caption=%s",
                        label,
                        result.get("date") or "-",
                        result.get("stats_raw") or "-",
                        f"{len(cap)} chars" if cap else "none",
                    )
                    if n < total:
                        delay = random.uniform(2.0, 4.0)
                        logger.info(
                            "%sWaiting %.1fs before the next post...", label, delay
                        )
                        time.sleep(delay)
                else:
                    captions_completed = True
                post_page.close()
            elif fetch_captions:
                captions_completed = False

            browser.close()

        if not items:
            logger.warning("No posts found. Check debug/%s.png", username)
            shutil.rmtree(staging, ignore_errors=True)
            return {"handle": username, "posts": []}

        # Downloads
        tasks: List[Tuple[str, str]] = []
        pfp_rel = "pfp.jpg"
        if pfp_url:
            tasks.append((pfp_url, os.path.join(staging, pfp_rel)))
        for i, item in enumerate(items, 1):
            item["orig_rel"] = f"posts/orig/post_{i}.jpg"
            item["web_rel"] = f"posts/web/post_{i}.webp"
            item["post_number"] = i
            tasks.append((item["src"], os.path.join(staging, item["orig_rel"])))

        ok = download_images_concurrently(tasks)

        posts: List[Dict[str, Any]] = []
        for item in items:
            orig_abs = os.path.join(staging, item["orig_rel"])
            if orig_abs not in ok:
                continue
            try:
                w, h = make_web_copy(orig_abs, os.path.join(staging, item["web_rel"]))
            except Exception as e:
                logger.warning(
                    "Could not make web copy for %s: %s", item["shortcode"], e
                )
                continue
            posts.append(
                {
                    "post_number": item["post_number"],
                    "shortcode": item["shortcode"],
                    "kind": item["kind"],
                    "url": f"https://www.instagram.com/{'reel' if item['kind'] == 'reel' else 'p'}/{item['shortcode']}/",
                    "web_path": item["web_rel"],
                    "orig_path": item["orig_rel"],
                    "width": w,
                    "height": h,
                    "source_width": item.get("source_width", 0),
                    "caption": item.get("caption", ""),
                    "alt_text": item.get("alt", ""),
                    "date": item.get("date") or date_from_alt(item.get("alt", "")),
                    "stats_raw": item.get("stats_raw", ""),
                    "raw_meta": item.get("raw_meta", ""),
                }
            )

        profile_data: Dict[str, Any] = {
            "name": name,
            "handle": username,
            "bio": bio,
            "followers": stat("Followers"),
            "following": stat("Following"),
            "post_count": stat("Posts"),
            "pfp_path": pfp_rel if os.path.join(staging, pfp_rel) in ok else "",
            "captions_are_real": captions_completed,
            "posts": posts,
        }

        if not posts:
            logger.warning("All downloads failed. Check debug/%s.png", username)
            shutil.rmtree(staging, ignore_errors=True)
            return profile_data

        with open(
            os.path.join(staging, "profile_data.json"), "w", encoding="utf-8"
        ) as f:
            json.dump(profile_data, f, indent=4, ensure_ascii=False)

        # Swap staging into place with retries for Windows file lock delays
        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                if os.path.exists(output_dir):
                    shutil.rmtree(output_dir)
                os.replace(staging, output_dir)
                break
            except (PermissionError, OSError):
                if attempt == max_attempts - 1:
                    raise
                time.sleep(0.4 * (attempt + 1))
        logger.info("Saved %d post(s) to %s", len(posts), json_final)
        return profile_data

    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def save_login_session(path: str) -> None:
    """Open a visible browser, let you log in manually, then save the session."""
    with sync_playwright() as p:
        browser = launch_browser(p, headless=False)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        page.goto("https://www.instagram.com/accounts/login/")
        input(
            "Log in in the browser window, then press Enter here to save the session..."
        )
        context.storage_state(path=path)
        browser.close()
    logger.info("Saved session to %s", path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape an Instagram profile's posts and info."
    )
    parser.add_argument("username", nargs="?", help="Instagram profile name")
    parser.add_argument("--max-posts", type=int, default=18)
    parser.add_argument(
        "--captions",
        action="store_true",
        help="Open each post to read the real caption/date (slower, riskier)",
    )
    parser.add_argument("--auth", default="auth.json", help="Saved login session file")
    parser.add_argument(
        "--save-auth",
        action="store_true",
        help="Log in manually once and save the session to --auth",
    )
    parser.add_argument(
        "--force", action="store_true", help="Re-scrape even if data exists"
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser window")
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()

    if args.save_auth:
        save_login_session(args.auth)
        return
    if not args.username:
        parser.error("username is required")

    data: Dict[str, Any] = {}
    for attempt in range(1, args.attempts + 1):
        try:
            data = scrape_profile(
                args.username,
                max_posts=args.max_posts,
                fetch_captions=args.captions,
                auth_path=args.auth,
                force=args.force,
                headed=args.headed,
            )
            if data.get("posts"):
                break
        except Exception as e:
            logger.error("Attempt %d/%d failed: %s", attempt, args.attempts, e)
            if any(marker in str(e) for marker in ("LOGIN_WALL:", "PRIVATE_ACCOUNT:", "ACCOUNT_UNAVAILABLE:")):
                break
        if attempt < args.attempts:
            wait = 5 * attempt
            logger.info("Retrying in %ds...", wait)
            time.sleep(wait)

    if not data.get("posts"):
        logger.error("No posts scraped for @%s. Aborting.", args.username)
        sys.exit(1)


if __name__ == "__main__":
    main()
