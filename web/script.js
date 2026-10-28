/* ==========================================================================
   Client-Side Password Protection & Hardcoded Users
   ==========================================================================
   To change usernames or passwords:
   1. Open your browser console (F12 -> Console) and run:
      (async (p) => {
        const b = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(p));
        console.log(Array.from(new Uint8Array(b)).map(x => x.toString(16).padStart(2, "0")).join(""));
      })("your_new_password")
   2. Copy the printed hash string.
   3. Update the username key and/or hash value in AUTH_USERS below.
   ========================================================================== */
const AUTH_USERS = {
  // username: SHA-256 hash of password
  user1: "e6c3da5b206634d7f3f3586d747ffdb36b5c675757b380c6a5fe5c570c714349", // pass1
  user2: "1ba3d16e9881959f8c9a9762854f72c6e6321cdd44358a10a4e939033117eab9", // pass2
};

async function sha256(str) {
  const buf = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(str),
  );
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function isAuthenticated() {
  const u = sessionStorage.getItem("studio_auth_user");
  return !!(u && AUTH_USERS[u]);
}

function showAuthOverlay() {
  document.documentElement.classList.remove("is-auth");
  const ov = $("#auth-overlay");
  if (ov) ov.hidden = false;
  const userIn = $("#auth-user");
  if (userIn) {
    userIn.value = "";
    setTimeout(() => userIn.focus(), 50);
  }
  const passIn = $("#auth-pass");
  if (passIn) passIn.value = "";
  const errEl = $("#auth-err");
  if (errEl) {
    errEl.hidden = true;
    errEl.textContent = "";
  }
}

function hideAuthOverlay() {
  document.documentElement.classList.add("is-auth");
  const ov = $("#auth-overlay");
  if (ov) ov.hidden = true;
  const passIn = $("#auth-pass");
  if (passIn) passIn.value = "";
}

function logout() {
  sessionStorage.removeItem("studio_auth_user");
  document.documentElement.classList.remove("is-auth");
  appInitialized = false;
  if (window._studioEventSource) {
    window._studioEventSource.close();
    window._studioEventSource = null;
  }
  const studio = $("#studio");
  if (studio) studio.hidden = true;
  const present = $("#present");
  if (present) present.hidden = true;
  const videoModal = $("#videomodal");
  if (videoModal) videoModal.hidden = true;
  showAuthOverlay();
  toast("Signed out");
}

const $ = (s, r = document) => r.querySelector(s),
  $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (x) =>
  String(x ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[c],
  );
const enc = encodeURIComponent;
function renderMarkdown(md) {
  if (!md || !md.trim()) return "";
  const lines = md.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
  const out = [];
  let inCode = false;
  let codeLang = "";
  let codeLines = [];
  let inList = null;
  let inBlockquote = false;
  let quoteLines = [];
  let paraLines = [];

  function inline(text) {
    let s = esc(text);
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*\*([^*]+)\*\*\*/g, "<strong><em>$1</em></strong>");
    s = s.replace(/___([^_]+)___/g, "<strong><em>$1</em></strong>");
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/__([^_]+)__/g, "<strong>$1</strong>");
    s = s.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    s = s.replace(/_([^_]+)_/g, "<em>$1</em>");
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, txt, url) => {
      const u = url.replace(/"/g, "&quot;").trim();
      if (/^(https?:\/\/|mailto:|\/|#)/i.test(u)) {
        return `<a href="${u}" target="_blank" rel="noopener noreferrer">${txt}</a>`;
      }
      return txt;
    });
    return s;
  }

  function flushPara() {
    if (paraLines.length > 0) {
      out.push("<p>" + paraLines.map(inline).join("<br/>") + "</p>");
      paraLines = [];
    }
  }
  function flushList() {
    if (inList) {
      out.push(`</${inList}>`);
      inList = null;
    }
  }
  function flushQuote() {
    if (inBlockquote) {
      out.push(
        "<blockquote>" + quoteLines.map(inline).join("<br/>") + "</blockquote>",
      );
      inBlockquote = false;
      quoteLines = [];
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const codeMatch = line.match(/^```(\w*)/);
    if (codeMatch) {
      if (inCode) {
        out.push(
          `<pre><code class="${codeLang}">${esc(codeLines.join("\n"))}</code></pre>`,
        );
        codeLines = [];
        inCode = false;
      } else {
        flushPara();
        flushList();
        flushQuote();
        inCode = true;
        codeLang = codeMatch[1] || "";
      }
      continue;
    }
    if (inCode) {
      codeLines.push(line);
      continue;
    }
    if (!line.trim()) {
      flushPara();
      flushList();
      flushQuote();
      continue;
    }
    const bqMatch = line.match(/^>\s?(.*)/);
    if (bqMatch) {
      flushPara();
      flushList();
      inBlockquote = true;
      quoteLines.push(bqMatch[1]);
      continue;
    } else {
      flushQuote();
    }
    const hMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (hMatch) {
      flushPara();
      flushList();
      const level = hMatch[1].length;
      out.push(`<h${level}>${inline(hMatch[2])}</h${level}>`);
      continue;
    }
    if (/^(\*{3,}|-{3,}|_{3,})$/.test(line.trim())) {
      flushPara();
      flushList();
      out.push("<hr />");
      continue;
    }
    const ulMatch = line.match(/^[\*\-]\s+(.+)$/);
    if (ulMatch) {
      flushPara();
      if (inList !== "ul") {
        flushList();
        inList = "ul";
        out.push("<ul>");
      }
      const content = ulMatch[1];
      const kvMatch = content.match(/^([^:\*_\`]+):\s+(.+)$/);
      if (kvMatch) {
        out.push(
          `<li><strong>${inline(kvMatch[1])}:</strong> ${inline(kvMatch[2])}</li>`,
        );
      } else {
        out.push(`<li>${inline(content)}</li>`);
      }
      continue;
    }
    const olMatch = line.match(/^\d+\.\s+(.+)$/);
    if (olMatch) {
      flushPara();
      if (inList !== "ol") {
        flushList();
        inList = "ol";
        out.push("<ol>");
      }
      out.push(`<li>${inline(olMatch[1])}</li>`);
      continue;
    }
    flushList();
    paraLines.push(line);
  }
  if (inCode) {
    out.push(
      `<pre><code class="${codeLang}">${esc(codeLines.join("\n"))}</code></pre>`,
    );
  }
  flushPara();
  flushList();
  flushQuote();
  return out.join("\n");
}
const ICONS = {
  board:
    '<rect x="3" y="3" width="5" height="18" rx="1"/><rect x="10" y="3" width="5" height="11" rx="1"/><rect x="17" y="3" width="4" height="15" rx="1"/>',
  batch: '<path d="M6 3l14 9-14 9z"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"/>',
  moon: '<path d="M20 14.5A8 8 0 019.5 4a8 8 0 1010.5 10.5z"/>',
  back: '<path d="M15 18l-6-6 6-6"/>',
  ext: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V7a1 1 0 011-1h5"/>',
  phone:
    '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
  tablet:
    '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M11 18h2"/>',
  monitor:
    '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  rec: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3" fill="currentColor"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/>',
  more: '<circle cx="5" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="19" cy="12" r="1.6" fill="currentColor"/>',
  check: '<path d="M5 12l5 5 9-10"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M4 20h16"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 00-1-1H5a1 1 0 00-1 1v10a1 1 0 001 1h3"/>',
  refresh: '<path d="M20 11a8 8 0 10-2.3 5.7M20 4v7h-7"/>',
  undo: '<path d="M9 14L4 9l5-5M4 9h10a6 6 0 010 12h-3"/>',
  send: '<path d="M21 3L10 14M21 3l-7 18-4-7-7-4z"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  expand: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>',
  list: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  side: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M15 4v16"/>',
  globe:
    '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
  chat: '<path d="M4 5h16v11H9l-5 4z"/>',
  play: '<path d="M6 3l14 9-14 9z"/>',
  users:
    '<path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/>',
  calendar:
    '<rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
  cloud:
    '<path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>',
  external:
    '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
  dollar:
    '<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
  info:
    '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
};
const ic = (n, s) =>
  `<svg class="i" viewBox="0 0 24 24"${s ? ` style="width:${s}px;height:${s}px"` : ""} aria-hidden="true">${ICONS[n] || ""}</svg>`;
const lab = (n, t) => `${ic(n)}<span>${t}</span>`;
const STAGES = ["new", "built", "recorded", "sent", "replied", "won", "lost"];
const ACTIVE_STAGES = ["new", "built", "recorded", "sent", "replied"];
const STATUSES = [
  "queued",
  "scraping",
  "building",
  "scraped",
  "done",
  "failed",
];
const S = {
  st: { leads: [], settings: {} },
  sel: "",
  ld: null,
  view: "pipeline",
  layout: localStorage.getItem("studio-layout") || "board",
  checked: new Set(),
  selmode: false,
  filter: "",
  nonce: Date.now(),
  nonces: {},
  device: "desktop",
  job: { active: false, handles: [] },
  sideOpen: true,
  logZoom: 11,
  loadingBatch: true,
};

/* ---------- theme ---------- */
function setTheme(t) {
  document.documentElement.dataset.theme = t === "light" ? "light" : "dark";
  localStorage.setItem("studio-theme", t === "light" ? "light" : "dark");
  $("#nav-theme").innerHTML =
    ic(t === "light" ? "moon" : "sun") +
    `<span>${t === "light" ? "Dark" : "Light"}</span>`;
}
function setPalette(p) {
  const v = ["studio", "ocean", "plum", "ember", "mono", "red"].includes(p)
    ? p
    : "studio";
  document.documentElement.dataset.palette = v;
  localStorage.setItem("studio-palette", v);
  drawSwatches();
}
function drawSwatches() {
  const cur = document.documentElement.dataset.palette;
  const cols = {
    studio: "#d9ff73",
    ocean: "#55d6d0",
    plum: "#c7a0ff",
    ember: "#ffae68",
    mono: "#a6a6a6",
    red: "#ff7b83",
  };
  $("#swatches").innerHTML = Object.entries(cols)
    .map(
      ([k, c]) =>
        `<button class="sw ${k === cur ? "on" : ""}" data-act="palette-set" data-p="${k}" style="background:${c};color:#111" aria-label="${k}">${k === cur ? ic("check") : ""}</button>`,
    )
    .join("");
}

/* ---------- utils ---------- */
const api = async (url, opt = {}) => {
  const headers = {
    "Content-Type": "application/json",
    "X-Studio": "1",
    ...(opt.headers || {}),
  };
  const r = await fetch(url, {
    ...opt,
    headers,
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Error(j.detail || r.statusText);
  return j;
};
const bq = () => {
  const b = $("#batch").value || S.st.batch;
  return b ? "?batch=" + enc(b) : "";
};
const leadUrl = (h) => `/api/lead/${enc(h)}`;
function bumpNonce(h) {
  if (!h) return;
  S.nonces[h] = Date.now();
  S.nonce = S.nonces[h];
}
function getNonce(h) {
  return (h && S.nonces[h]) || "";
}
const previewUrl = (h) => {
  const n = getNonce(h);
  return `/preview/${enc(S.st.batch)}/${enc(h)}/index.html${n ? `?t=${n}` : ""}`;
};
function toast(s) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = s;
  $("#toasts").append(t);
  setTimeout(() => t.remove(), 2800);
}
function setSyncIndicator(msg) {
  const p = $("#syncpill");
  if (!p) return;
  if (!msg) {
    p.hidden = true;
    return;
  }
  $("#synctext").textContent = msg;
  p.hidden = false;
}
const debounce = (f, ms) => {
  let t;
  return (...a) => {
    clearTimeout(t);
    t = setTimeout(() => f(...a), ms);
  };
};
function hue(s) {
  let h = 0;
  for (const c of String(s)) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}
const initial = (l) =>
  ((l.name || l.handle || "?").trim()[0] || "?").toUpperCase();
const avatarHtml = (l, style = "") =>
  `<div class="avatar" style="${style || `background:hsl(${hue(l.handle)} 45% 40%)`}">${esc(initial(l))}<img src="/media/${enc(S.st.batch)}/${enc(l.handle)}/pfp.jpg" alt="" onerror="this.remove()" draggable="false" /></div>`;
const stageOf = (l) => (STAGES.includes(l.stage) ? l.stage : "new");
let dlgRes = null;
function dlg(title, body, buttons) {
  return new Promise((res) => {
    dlgRes = res;
    $("#dlgtitle").textContent = title;
    $("#dlgbody").textContent = body;
    const a = $("#dlgactions");
    a.innerHTML = "";
    buttons.forEach((b) => {
      const el = document.createElement("button");
      el.textContent = b.label;
      if (b.cls) el.className = b.cls;
      el.onclick = () => {
        $("#dlgov").hidden = true;
        dlgRes = null;
        res(b.value);
      };
      a.append(el);
    });
    $("#dlgov").hidden = false;
    a.querySelector("button:last-child")?.focus();
  });
}
const confirmDlg = (t, b, ok) =>
  dlg(t, b, [
    { label: "Cancel", value: false },
    { label: ok, value: true, cls: "primary" },
  ]);
const leadOf = (h) => S.st.leads.find((x) => x.handle === h) || { handle: h };
const hasSite = () => !!(S.ld && S.ld.lead && S.ld.lead.site_path);

/* ---------- data ---------- */
async function refresh(reload) {
  try {
    S.st = await api("/api/state" + bq());
    S.loadingBatch = false;
    $("#batch").value = S.st.batch;
    $("#batch").disabled = false;
    $("#batch").classList.remove("loading-date");
    $("#batch").title = `Batch date: ${S.st.batch}`;
    setSyncIndicator(null);
    if (S.st.needs_setup) {
      openSetupModal();
    } else {
      closeSetupModal();
    }
    if ($("#offlinebanner"))
      $("#offlinebanner").hidden = !(S.st.local_mode || S.st.d1_offline);
    if (document.activeElement !== $("#accounts"))
      $("#accounts").value = S.st.accounts || "";
    const s = S.st.settings || {};
    if (S.view !== "settings" || !$("#sroot").dataset.filled) {
      fillSettings();
    }
    $("#authstate").textContent = S.st.auth_exists
      ? "Session saved · " + S.st.auth_mtime
      : "No session";
    render();
    if (reload && S.sel && !$("#studio").hidden) await loadLead(S.sel, false);
    await jobStatus();
  } catch (e) {
    S.loadingBatch = false;
    $("#batch").disabled = false;
    $("#batch").classList.remove("loading-date");
    setSyncIndicator(null);
    await jobStatus();
    throw e;
  }
}
async function jobStatus() {
  try {
    S.job = await api("/api/job");
  } catch {}
  const a = S.job.active;
  $("#jobpill").classList.toggle("run", !!a);
  $("#jobtext").textContent = a
    ? S.job.batch_active
      ? `Running · ${(S.job.handles || []).length} queued`
      : `Revision${S.job.revision_pending > 1 ? "s" : ""} · ${S.job.revision_pending} queued`
    : "Ready";
  $("#cancel").hidden = !S.job.batch_active;
  $("#b-rev").disabled = !!S.job.batch_active;
  $("#revision").disabled = !!S.job.batch_active;
  $$('[data-act="reapply"]').forEach(
    (b) => (b.disabled = !!S.job.batch_active),
  );
  $$('[data-act="run"]').forEach((b) => (b.disabled = !!S.job.active));
}
const refreshSoon = debounce(() => refresh(false), 350);

/* ---------- views ---------- */
function setView(v) {
  S.view = v;
  ["pipeline", "clients", "batch", "settings"].forEach((x) => {
    const el = $("#view-" + x);
    if (el) el.hidden = x !== v;
    $("#nav-" + x)?.classList.toggle("active", x === v);
  });
  const meta = {
    pipeline: ["Pipeline", "Manage your website mockups"],
    clients: ["Clients", "Won deals, revenue & client fulfillment"],
    batch: ["Batch Studio", "Prepare accounts and run mockup pipeline"],
    settings: ["Settings", "Configure workspace, models & storage"],
  }[v];
  if (meta) {
    if ($("#viewtitle")) $("#viewtitle").textContent = meta[0];
    if ($("#viewsubtitle")) $("#viewsubtitle").textContent = meta[1];
  }
  if (v === "settings") fillSettings();
  render();
}
function filtered() {
  const q = ($("#q").value || "").toLowerCase();
  return (S.st.leads || []).filter(
    (x) =>
      (!q ||
        [x.handle, x.name, x.area, x.phone]
          .join(" ")
          .toLowerCase()
          .includes(q)) &&
      (!S.filter || x.status === S.filter),
  );
}
function render() {
  const allLeads = S.st.leads || [];
  const wonLeads = allLeads.filter((l) => stageOf(l) === "won");
  const activeLeads = allLeads.filter(
    (l) => !["won", "lost"].includes(stageOf(l)),
  );
  if ($("#count-pipeline")) $("#count-pipeline").textContent = activeLeads.length;
  if ($("#count-clients")) $("#count-clients").textContent = wonLeads.length;
  if ($("#lay-board"))
    $("#lay-board").classList.toggle("on", S.layout === "board");
  if ($("#lay-list"))
    $("#lay-list").classList.toggle("on", S.layout === "list");
  if ($("#selbtn")) $("#selbtn").textContent = S.selmode ? "Done" : "Select";
  renderChips();
  if (S.view === "pipeline") renderPipeline();
  if (S.view === "clients") renderClients();
  if (S.view === "batch") renderBatch();
  renderSelbar();
}
function renderChips() {
  if (S.loadingBatch) {
    $("#statuschips").innerHTML =
      `<span class="chip on" style="opacity:0.75;cursor:wait"><span>Finding latest date…</span></span>`;
    return;
  }
  const counts = {};
  (S.st.leads || []).forEach(
    (l) => (counts[l.status] = (counts[l.status] || 0) + 1),
  );
  $("#statuschips").innerHTML =
    `<button class="chip ${S.filter ? "" : "on"}" data-act="filter" data-f="">All · ${(S.st.leads || []).length}</button>` +
    STATUSES.filter((s) => counts[s])
      .map(
        (s) =>
          `<button class="chip ${S.filter === s ? "on" : ""}" data-act="filter" data-f="${s}">${s} · ${counts[s]}</button>`,
      )
      .join("");
}
function cardHtml(l) {
  const h = esc(l.handle),
    picked = S.checked.has(l.handle);
  const fail =
    l.status === "failed"
      ? `<div class="cardfail">${ic("x", 12)}<span>Build failed</span><button class="sm" data-act="retry" data-h="${h}">Retry</button></div>`
      : "";
  const isCloud =
    l.site_path &&
    (l.site_path.startsWith("http") || l.site_path.startsWith("/preview/"));
  const cloudBadge = isCloud
    ? `<span class="cloud-badge" title="Hosted in Cloudflare R2">${ic("cloud", 11)} R2</span>`
    : "";
  const hasRec = !!(
    l.has_recording ||
    (l.recordings && Object.keys(l.recordings).length)
  );
  const recBadge = hasRec
    ? `<button class="demo-badge sm" data-act="playCardRec" data-h="${h}" title="Watch video demo">${ic("play", 10)} Demo</button>`
    : "";

  const _now = new Date();
  const today = `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, "0")}-${String(_now.getDate()).padStart(2, "0")}`;
  const isDueToday =
    l.follow_up &&
    l.follow_up <= today &&
    !["won", "lost"].includes(stageOf(l));
  const dueBadge = l.follow_up
    ? `<span class="card-due ${isDueToday ? "due-today" : ""}" title="Follow-up due date">${ic("calendar", 11)} ${esc(l.follow_up)}</span>`
    : "";

  const priceBadge = l.price
    ? `<span class="deal-badge" title="Quoted deal price">$${esc(String(l.price).replace(/^\$/, ""))}</span>`
    : "";

  const st = stageOf(l);
  const isPitchStage = ["sent", "replied"].includes(st);

  return `<div class="card ${picked ? "picked" : ""}" draggable="true" data-act="open" data-h="${h}" tabindex="0">
    <div class="card-row">
      ${S.selmode ? `<input type="checkbox" ${picked ? "checked" : ""} data-act="check" data-h="${h}" aria-label="Select ${h}" />` : ""}
      ${avatarHtml(l)}
      <div class="card-info">
        <div class="card-name">${esc(l.name || "@" + l.handle)}</div>
        <div class="card-meta">@${h}${l.area ? " · " + esc(l.area) : ""}</div>
      </div>
    </div>

    <div class="card-badges">
      <span class="status ${esc(l.status || "queued")}">${esc(l.status || "queued")}</span>
      ${priceBadge}
      ${cloudBadge}
      ${recBadge}
      ${dueBadge}
    </div>

    <div class="card-actions">
      ${l.site_path ? `<button class="sm ghost card-btn" data-act="openPreviewTab" data-h="${h}" title="View website in new tab">${ic("external", 11)}<span>Site</span></button>` : ""}
      ${l.phone ? `<button class="sm ghost card-btn" data-act="cardWa" data-h="${h}" title="Open WhatsApp chat">${ic("chat", 11)}<span>WhatsApp</span></button>` : ""}
      ${isPitchStage ? `<button class="sm win-btn card-btn" data-act="cardMarkWon" data-h="${h}" title="Mark as Won (Closed Deal)">✓ Won</button>` : ""}
      ${isPitchStage ? `<button class="sm loss-btn card-btn" data-act="cardMarkLost" data-h="${h}" title="Archive as Lost">✕ Pass</button>` : ""}
      <div class="menu" style="margin-left:auto">
        <button class="sm ghost card-btn" data-act="cardMenu" data-h="${h}" title="More lead actions" aria-label="More actions for ${h}">${ic("more", 11)}</button>
        <div class="menulist card-menulist" id="cardmenu-${h}" hidden>
          <button data-act="open" data-h="${h}">${ic("side", 12)}Open Studio</button>
          ${l.site_path ? `<button data-act="openPreviewTab" data-h="${h}">${ic("external", 12)}View Site ↗</button>` : ""}
          ${l.phone ? `<button data-act="cardWa" data-h="${h}">${ic("chat", 12)}WhatsApp Pitch</button>` : ""}
          <button data-act="cardCopyPitch" data-h="${h}">${ic("copy", 12)}Copy Pitch Text</button>
          <button data-act="cardRebuild" data-h="${h}">${ic("refresh", 12)}Rebuild Site</button>
          ${l.site_path ? `<button data-act="cardZip" data-h="${h}">${ic("download", 12)}Download Site ZIP</button>` : ""}
          <div class="menu-divider"></div>
          <button class="danger" data-act="cardMarkLost" data-h="${h}">Archive Lead (Lost)</button>
        </div>
      </div>
    </div>
    ${fail}
  </div>`;
}
function renderPipeline() {
  const rows = filtered();
  const _now = new Date();
  const today = `${_now.getFullYear()}-${String(_now.getMonth() + 1).padStart(2, "0")}-${String(_now.getDate()).padStart(2, "0")}`;
  const due = (S.st.leads || []).filter(
    (l) =>
      l.follow_up &&
      l.follow_up <= today &&
      !["won", "lost"].includes(stageOf(l)),
  );
  const d = $("#due");
  d.hidden = !due.length;
  d.innerHTML = due.length
    ? `<b>Follow-ups due</b>` +
      due
        .map(
          (l) =>
            `<button class="sm" data-act="open" data-h="${esc(l.handle)}">${esc(l.name || "@" + l.handle)}</button>`,
        )
        .join("")
    : "";
  const root = $("#pipeline");
  if (S.loadingBatch) {
    root.innerHTML = `<div class="empty" style="padding: 70px 16px;">
            <div class="loader-spinner" style="margin: 0 auto 16px;"></div>
            <h3 style="font-size: 16px; margin-bottom: 6px; color: var(--text);">Finding latest date…</h3>
            <div class="muted" style="font-size: 13px;">Connecting to database and loading the newest batch</div>
          </div>`;
    return;
  }
  if (!(S.st.leads || []).length) {
    root.innerHTML = `<div class="empty"><h3>No leads yet</h3>Add Instagram accounts in Batch to start building sites.<br><br><button class="primary" data-act="view" data-v="batch">Add accounts</button></div>`;
    return;
  }
  if (S.layout === "board") {
    root.innerHTML =
      `<div class="board">` +
      ACTIVE_STAGES.map((st) => {
        const c = rows.filter((l) => stageOf(l) === st);
        return `<div class="col" data-stage="${st}">
                <div class="colhead">
                  <span class="stage-dot"></span>
                  <span>${st}</span>
                  <span class="n">${c.length}</span>
                </div>
                <div class="col-cards">
                  ${c.map(cardHtml).join("") || '<div class="empty-drop">Drop lead here</div>'}
                </div>
              </div>`;
      }).join("") +
      `</div>`;
  } else {
    root.innerHTML = rows.length
      ? `<div class="list-wrap"><div class="table-card"><table class="list"><thead><tr>${S.selmode ? '<th style="width:40px"></th>' : ""}<th>Lead</th><th>Status</th><th>Stage</th><th>Area</th><th>Phone</th></tr></thead><tbody>` +
        rows
          .map(
            (l) =>
              `<tr class="${S.checked.has(l.handle) ? "picked" : ""}" data-act="open" data-h="${esc(l.handle)}">${S.selmode ? `<td><input type="checkbox" ${S.checked.has(l.handle) ? "checked" : ""} data-act="check" data-h="${esc(l.handle)}"></td>` : ""}<td><div style="display:flex;gap:10px;align-items:center">${avatarHtml(l, "width:32px;height:32px;font-size:13px;background:hsl(" + hue(l.handle) + " 45% 40%)")}<div><div style="font-weight:650">${esc(l.name || "@" + l.handle)}</div><div class="muted" style="font-size:12px">@${esc(l.handle)}</div></div></div></td><td><span class="status ${esc(l.status)}">${esc(l.status || "queued")}</span> ${l.site_path && (l.site_path.startsWith("http") || l.site_path.startsWith("/preview/")) ? `<span class="cloud-badge">${ic("cloud", 11)} R2</span>` : ""} ${l.has_recording || (l.recordings && Object.keys(l.recordings).length) ? `<button class="demo-badge sm" data-act="playCardRec" data-h="${esc(l.handle)}" title="Watch video demo">${ic("play", 10)} Demo</button>` : ""}</td><td>${esc(stageOf(l))}</td><td>${esc(l.area || "—")}</td><td>${esc(l.phone || "—")}</td></tr>`,
          )
          .join("") +
        `</tbody></table></div></div>`
      : `<div class="empty"><h3>No matches</h3>Try a different filter.</div>`;
  }
}
function renderClients() {
  const allLeads = S.st.leads || [];
  const wonLeads = allLeads.filter((l) => stageOf(l) === "won");
  const q = ($("#q-clients")?.value || "").trim().toLowerCase();
  const filtered = wonLeads.filter((l) => {
    if (!q) return true;
    return [l.name, l.handle, l.phone, l.area, l.notes, l.price]
      .filter(Boolean)
      .join(" ")
      .toLowerCase()
      .includes(q);
  });

  let totalRev = 0;
  wonLeads.forEach((l) => {
    const num = parseFloat(String(l.price || "").replace(/[^0-9.]/g, ""));
    if (!isNaN(num) && num > 0) totalRev += num;
  });
  const avgDeal = wonLeads.length ? Math.round(totalRev / wonLeads.length) : 0;

  if ($("#metric-clients-count"))
    $("#metric-clients-count").textContent = wonLeads.length;
  if ($("#metric-clients-rev"))
    $("#metric-clients-rev").textContent = `$${totalRev.toLocaleString()}`;
  if ($("#metric-clients-avg"))
    $("#metric-clients-avg").textContent = `$${avgDeal.toLocaleString()}`;

  const tbody = $("#clients-tbody");
  const empty = $("#clients-empty");
  if (!tbody) return;

  if (!filtered.length) {
    tbody.innerHTML = "";
    if (empty) empty.hidden = false;
    return;
  }
  if (empty) empty.hidden = true;

  tbody.innerHTML = filtered
    .map((l) => {
      const h = esc(l.handle);
      const priceDisplay = l.price
        ? `<span class="deal-badge">$${esc(String(l.price).replace(/^\$/, ""))}</span>`
        : `<span class="muted" style="font-size:11px">—</span>`;
      const phoneClean = (l.phone || "").replace(/\D/g, "");
      const waBtn = phoneClean
        ? `<button class="sm ghost card-btn" data-act="cardWa" data-h="${h}" title="Message on WhatsApp">${ic("chat", 12)}<span>WhatsApp</span></button>`
        : `<span class="muted" style="font-size:11px">${esc(l.phone || "No phone")}</span>`;
      const siteBtn = l.site_path
        ? `<button class="sm ghost card-btn" data-act="openPreviewTab" data-h="${h}" title="View live site mockup in new tab">${ic("external", 12)}<span>View Site</span></button>`
        : `<span class="muted" style="font-size:11px">No site</span>`;
      const zipBtn = `<a class="sm ghost card-btn" href="/api/lead/${enc(l.handle)}/zip?mode=site" download="${h}-site.zip" title="Download Site ZIP">${ic("download", 12)}<span>Site ZIP</span></a>`;
      const updateDate = l.updated_at
        ? esc(l.updated_at.split("T")[0] || l.updated_at.split(" ")[0])
        : "—";

      return `<tr>
        <td>
          <div style="display:flex;gap:10px;align-items:center">
            ${avatarHtml(l, "width:34px;height:34px;font-size:13px;border-radius:6px;background:hsl(" + hue(l.handle) + " 45% 40%)")}
            <div>
              <div style="font-weight:600;font-size:13px">${esc(l.name || "@" + l.handle)}</div>
              <div class="muted" style="font-size:11px">@${h}${l.area ? " · " + esc(l.area) : ""}</div>
            </div>
          </div>
        </td>
        <td>${priceDisplay}</td>
        <td>${waBtn}</td>
        <td>${siteBtn}</td>
        <td>${zipBtn}</td>
        <td><span class="muted" style="font-size:11px">${updateDate}</span></td>
        <td>
          <div style="display:flex;gap:6px;align-items:center">
            <button class="sm ghost" data-act="open" data-h="${h}" title="Open Lead Studio">Studio</button>
            <button class="sm ghost" data-act="reopenLead" data-h="${h}" title="Move back to Pipeline (Replied)">Reopen</button>
          </div>
        </td>
      </tr>`;
    })
    .join("");
}
function renderSelbar() {
  let b = $("#selbar");
  if (!S.selmode || !S.checked.size || S.view !== "pipeline") {
    b && b.remove();
    return;
  }
  if (!b) {
    b = document.createElement("div");
    b.id = "selbar";
    b.className = "selbar";
    document.body.append(b);
  }
  b.innerHTML = `<b>${S.checked.size} selected</b><button class="primary sm" data-act="runChecked">Run</button><button class="sm danger" data-act="deleteChecked">Delete</button><button class="sm ghost" data-act="selmode">Cancel</button>`;
}
function renderBatch() {
  $$('[data-act="run"]').forEach(
    (b) => (b.innerHTML = lab("play", "Run batch")),
  );
  const leads = S.st.leads || [];
  const complete = leads.filter((l) =>
      ["done", "scraped"].includes(l.status),
    ).length,
    fail = leads.filter((l) => l.status === "failed").length;
  $("#runsummary").textContent = leads.length
    ? `${complete} complete · ${fail} failed · ${leads.length - complete - fail} in progress or queued`
    : "No activity yet.";
  $("#runbar").style.width = leads.length
    ? Math.round(((complete + fail) / leads.length) * 100) + "%"
    : "0%";
  $("#runs").innerHTML = leads
    .map((l) => {
      const s = l.status;
      const order = {
        queued: 0,
        scraping: 1,
        building: 2,
        scraped: 3,
        done: 3,
        failed: -1,
      };
      const n = order[s] ?? 0;
      const step = (i, t) =>
        `<span class="step ${s === "failed" && i === Math.max(n, 0) ? "bad" : n > i || ["done", "scraped"].includes(s) ? "ok" : n === i ? "cur" : ""}">${t}</span>`;
      const step2 = $("#scrape-only").checked ? "Sheets" : "Build";
      return `<div class="run"><div><b>${esc(l.name || "@" + l.handle)}</b> <span class="muted">@${esc(l.handle)}</span><div class="track">${step(1, "Scrape")}${step(2, step2)}${step(3, "Done")}</div></div><div><button class="sm" data-act="open" data-h="${esc(l.handle)}">Open</button></div></div>`;
    })
    .join("");
}

/* ---------- studio ---------- */
function syncStudioLead(l, overwrite = false) {
  if (!l) return;
  const h = l.handle || S.sel;
  const isEditing = (el) => el && document.activeElement === el;

  if (overwrite || !isEditing($("#f-name"))) {
    $("#f-name").value = l.name || "";
    $("#f-name").placeholder = l.name || "@" + h;
  }
  $("#ssub").textContent = `@${h}${l.area ? " · " + l.area : ""}`;
  $("#previewurl").textContent = l.site_path || "";

  ["area", "phone", "followers", "price", "notes", "follow_up"].forEach((k) => {
    const el = $("#f-" + k);
    if (overwrite || !isEditing(el)) {
      el.value = l[k] || "";
    }
  });
  if (overwrite || !isEditing($("#f-stage"))) {
    $("#f-stage").value = stageOf(l);
  }
  $("#f-qa").value = l.qa || (l.site_path ? "Built" : "Pending build QA");
  updateContactMenu();
  const hasRec = !!(
    l.has_recording ||
    (S.ld?.recordings && Object.keys(S.ld.recordings).length)
  );
  if ($("#playrecbtn")) $("#playrecbtn").hidden = !hasRec;
  drawStrip();
  drawNext();
}

async function openStudio(h) {
  S.sel = h;
  $("#revisionlogs").innerHTML = "";
  $("#studio").hidden = false;
  document.body.style.overflow = "hidden";
  paintStudioChrome();

  // 1. Immediately look up known lead metadata from in-memory cache
  const l = leadOf(h);
  S.ld = {
    lead: { ...l },
    profile: {},
    summary: [],
    revisions: [],
    design: "",
    selected_photos: [],
    recordings: l.has_recording ? { desktop: "" } : {},
    cloud_newer: false,
  };

  // 2. Immediately populate business name, handle, action buttons, and lead fields
  syncStudioLead(l, true);

  // 3. Clear async tab content so previous lead's data is never displayed
  $("#biotext").textContent = "Profile data appears after scraping…";
  $("#history").innerHTML =
    '<div class="muted">No revisions yet. Describe a change below.</div>';
  $("#photos").innerHTML = '<div class="muted">Loading photos…</div>';
  $("#photocount").textContent = "";
  $("#designtext").innerHTML =
    '<div class="muted">Loading design direction…</div>';

  // 4. Reset preview iframe and show loader for this specific lead
  const f = $("#preview");
  f.removeAttribute("src");
  delete f.dataset.base;
  f.hidden = true;
  $("#previewempty").hidden = true;

  const ldr = $("#deviceloader");
  if (ldr) {
    ldr.classList.remove("fade-out");
    ldr.hidden = false;
    $("#loaderhandle").textContent = `@${h}`;
    $("#loaderstatus").textContent = "Connecting to Cloudflare R2…";
    $("#loadersub").textContent = "Fetching mockup, assets & recordings";
  }
  setSyncIndicator(`Loading @${h} from R2…`);

  try {
    await loadLead(h, true);
  } finally {
    if (S.sel === h) setSyncIndicator(null);
  }
}

function closeStudio() {
  S.sel = "";
  S.ld = null;
  $("#studio").hidden = true;
  document.body.style.overflow = "";
  const f = $("#preview");
  f.removeAttribute("src");
  delete f.dataset.base;
  $("#f-name").value = "";
  $("#ssub").textContent = "@handle";
  $("#strip").innerHTML = "";
  $("#nextbtn").innerHTML = "";
  const ldr = $("#deviceloader");
  if (ldr) ldr.hidden = true;
  $("#smenu").hidden = true;
  if ($("#playrecbtn")) $("#playrecbtn").hidden = true;
  setSyncIndicator(null);
  refresh(false);
}
function paintStudioChrome() {
  $("#ic-back").innerHTML = ic("back");
  $("#ic-more").innerHTML = ic("more");
  $("#presentbtn").innerHTML = lab("expand", "Present");
  $("#playrecbtn").innerHTML = lab("play", "Watch Demo");
  $("#d-phone").innerHTML = ic("phone");
  $("#d-tablet").innerHTML = ic("tablet");
  $("#d-desktop").innerHTML = ic("monitor");
  $("#b-reload").innerHTML = lab("refresh", "Reload");
  $("#b-side").innerHTML = ic("side");
  $("#b-buildnow").innerHTML = lab("play", "Build site");
  $("#b-rev").innerHTML = lab("send", "Apply change");
  $("#m-rebuild").innerHTML = lab("refresh", "Rebuild site");
  $("#m-open").innerHTML = lab("ext", "Open in new tab");
  $("#m-ig").innerHTML = lab("globe", "Instagram profile");
  $("#m-wa").innerHTML = lab("chat", "WhatsApp");
  $("#m-pitch").innerHTML = lab("copy", "Copy pitch");
  $("#m-path").innerHTML = lab("copy", "Copy site path");
  $("#m-zip").innerHTML = lab("download", "Download Site ZIP");
  $("#m-zip-full").innerHTML = lab("download", "Download Full Folder ZIP");
  $("#m-rec-dl").innerHTML = lab("play", "Download Recording");
  $("#m-rec-del").innerHTML = lab("trash", "Delete Recording…");
  $("#m-del").innerHTML = lab("trash", "Delete lead…");
  $("#p-exit").innerHTML = lab("back", "Exit");
  $("#p-full").innerHTML = lab("expand", "Fullscreen");
  $("#p-rec").innerHTML = lab("rec", "Start recording");
  $("#p-rec").setAttribute("aria-label", "Start recording");
}
async function loadLead(h, full) {
  try {
    const d = await api(leadUrl(h) + bq());
    if (h !== S.sel) return;
    S.ld = d;
    const l = d.lead;
    syncStudioLead(l, full);

    const built = !!(l.site_path && l.site_path.length);
    const f = $("#preview");
    const ldr = $("#deviceloader");
    if (!built) {
      if (ldr) ldr.hidden = true;
      f.hidden = true;
      $("#previewempty").hidden = false;
    } else {
      $("#previewempty").hidden = true;
      if (d.cloud_newer) {
        bumpNonce(h);
      }
      const base = `/preview/${enc(S.st.batch)}/${enc(h)}/index.html`;
      const curNonce = getNonce(h);
      const targetBase = base + (curNonce ? `?t=${curNonce}` : "");
      if (full || !f.dataset.base || f.dataset.base !== targetBase) {
        f.dataset.base = targetBase;
        f.hidden = true;
        if (ldr) {
          ldr.classList.remove("fade-out");
          ldr.hidden = false;
          if (d.cloud_newer) {
            $("#loaderstatus").textContent =
              "Pulling latest revision from R2…";
            $("#loadersub").textContent =
              "Syncing updated site files to local disk";
          } else {
            $("#loaderstatus").textContent = "Rendering website preview…";
            $("#loadersub").textContent = "";
          }
        }
        const purl = previewUrl(h);
        f.onload = () => {
          if (h === S.sel) {
            if (ldr) {
              ldr.classList.add("fade-out");
              setTimeout(() => {
                if (h === S.sel) ldr.hidden = true;
              }, 250);
            }
            f.hidden = false;
            if (d.cloud_newer) {
              toast("Synced latest revision from Cloudflare R2!");
            }
          }
        };
        f.onerror = () => {
          if (h === S.sel) {
            if (ldr) ldr.hidden = true;
            f.hidden = true;
            $("#previewempty").hidden = false;
          }
        };
        f.src = purl;
      } else {
        if (ldr) ldr.hidden = true;
        f.hidden = false;
      }
    }
    const recBtn = $("#m-rec-dl");
    const delRecBtn = $("#m-rec-del");
    const playRecBtn = $("#playrecbtn");
    const hasRec = d.recordings && Object.keys(d.recordings).length > 0;
    if (recBtn) {
      recBtn.hidden = !hasRec;
      if (hasRec) {
        const recDevs = Object.keys(d.recordings).join("/");
        recBtn.innerHTML = lab("play", `Download Recording (${recDevs})`);
      }
    }
    if (delRecBtn) {
      delRecBtn.hidden = !hasRec;
    }
    if (playRecBtn) {
      playRecBtn.hidden = !hasRec;
    }
    $("#f-qa").value = l.qa || "";
    $("#biotext").textContent =
      d.profile?.bio || "Profile data appears after scraping.";
    drawPhotos();
    drawRevisions();
    $("#designtext").innerHTML =
      d.design && d.design.trim()
        ? renderMarkdown(d.design)
        : '<div class="muted">No design direction generated yet.</div>';
  } catch (e) {
    toast(e.message);
  }
}
function drawStrip() {
  const l = S.ld?.lead || leadOf(S.sel),
    cur = STAGES.indexOf(stageOf(l)),
    built = hasSite();
  const steps = [
    ["built", "Built"],
    ["recorded", "Recorded"],
    ["sent", "Sent"],
    ["replied", "Replied"],
  ];
  let nextMarked = false;
  $("#strip").innerHTML = steps
    .map(([k, t]) => {
      const idx = STAGES.indexOf(k);
      const ok = (k === "built" && built) || cur >= idx;
      let cls = ok ? "ok" : "";
      if (!ok && !nextMarked) {
        cls = "next";
        nextMarked = true;
      }
      return `<li><button class="${cls}" data-act="setstage" data-s="${k}">${ok ? "✓ " : ""}${t}</button></li>`;
    })
    .join("");
}
function drawNext() {
  const l = S.ld?.lead || leadOf(S.sel),
    st = stageOf(l),
    b = $("#nextbtn"),
    busy = ["queued", "scraping", "building"].includes(leadOf(S.sel).status);
  let txt,
    ico,
    act = "next";
  if (!hasSite()) {
    txt = busy ? "Building…" : "Build site";
    ico = "play";
    b.disabled = busy;
  } else {
    b.disabled = false;
    if (st === "new" || st === "built") {
      txt = "Record walkthrough";
      ico = "rec";
    } else if (st === "recorded") {
      txt = hasPhone()
        ? "Copy pitch & open WhatsApp"
        : "Copy pitch & open Instagram";
      ico = "send";
    } else if (st === "sent") {
      txt = "Mark replied";
      ico = "check";
    } else if (st === "replied") {
      txt = "Mark won";
      ico = "check";
    } else {
      txt = "Closed · " + st;
      ico = "check";
      b.disabled = true;
    }
  }
  b.innerHTML = lab(ico, txt);
}
function hasPhone() {
  return !!String($("#f-phone").value || "").replace(/\D/g, "");
}
function updateContactMenu() {
  const phone = hasPhone();
  $("#m-wa").hidden = !phone;
  $("#m-ig").hidden = phone;
  $("#m-ig").innerHTML = lab("globe", "Open Instagram");
}
function drawPhotos() {
  const posts = S.ld.profile?.posts || [];
  const chosen = new Set(S.ld.selected_photos || []);
  const fn = (p) => (p.web_path || "").split("/").pop();
  $("#photos").innerHTML =
    posts
      .map(
        (p) =>
          `<button class="tile ${chosen.has(fn(p)) ? "on" : ""}" data-act="photo" data-f="${esc(fn(p))}" title="${esc(p.caption || p.alt_text || "Post image")}"><img src="${esc(p.preview)}" alt="${esc(p.alt_text || "")}" loading="lazy"><span class="tick">${ic("check")}</span></button>`,
      )
      .join("") || '<div class="muted">No scraped photos yet.</div>';
  updatePhotoCount();
}
function updatePhotoCount() {
  const n = $$(".tile.on").length,
    t = $$(".tile").length;
  $("#photocount").textContent = t
    ? `${n} of ${t} images allowed in the site`
    : "";
}
const savePhotos = debounce(async () => {
  const files = $$(".tile.on").map((x) => x.dataset.f);
  try {
    await api(`${leadUrl(S.sel)}/photos${bq()}`, {
      method: "PUT",
      body: JSON.stringify({ files }),
    });
    flashSaved();
  } catch (e) {
    toast(e.message);
  }
}, 500);
function drawRevisions() {
  const r = S.ld.revisions || [];
  $("#history").innerHTML =
    r
      .map(
        (x) =>
          `<div class="rev"><div>${esc(x.request)}</div><div class="rh"><span class="status ${x.status === "applied" ? "done" : ""}">${esc(x.status)}</span><span class="spacer"></span><button class="sm" data-act="reapply" data-id="${x.id}" ${S.job.batch_active ? "disabled" : ""}>${ic("refresh", 14)} Rerun</button>${x.backup_path ? `<button class="sm" data-act="undorev" data-id="${x.id}">${ic("undo", 14)} Undo</button>` : ""}</div></div>`,
      )
      .join("") ||
    '<div class="muted">No revisions yet. Describe a change below.</div>';
}
function flashSaved() {
  const s = $("#saved");
  s.classList.add("show");
  clearTimeout(flashSaved.t);
  flashSaved.t = setTimeout(() => s.classList.remove("show"), 1500);
}
async function putLead(extra = {}) {
  if (!S.sel) return;
  const body = {
    name: $("#f-name").value,
    phone: $("#f-phone").value,
    area: $("#f-area").value,
    followers: $("#f-followers").value,
    notes: $("#f-notes").value,
    stage: $("#f-stage").value,
    follow_up: $("#f-follow_up").value,
    price: $("#f-price").value,
    ...extra,
  };
  await api(`${leadUrl(S.sel)}${bq()}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
  if (extra.stage) $("#f-stage").value = extra.stage;
  flashSaved();
}
let autosaveTimer = null;
function autosave() {
  const targetHandle = S.sel;
  if (!targetHandle) return;
  const body = {
    name: $("#f-name").value,
    phone: $("#f-phone").value,
    area: $("#f-area").value,
    followers: $("#f-followers").value,
    notes: $("#f-notes").value,
    stage: $("#f-stage").value,
    follow_up: $("#f-follow_up").value,
    price: $("#f-price").value,
  };
  clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(async () => {
    try {
      await api(`${leadUrl(targetHandle)}${bq()}`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      flashSaved();
      const l = leadOf(targetHandle);
      if (l) {
        Object.assign(l, {
          name: body.name,
          phone: body.phone,
          stage: body.stage,
        });
      }
      if (S.sel === targetHandle) {
        $("#ssub").textContent =
          `@${targetHandle}${body.area ? " · " + body.area : ""}`;
        if (S.ld) {
          S.ld.lead.stage = body.stage;
          drawStrip();
          drawNext();
          updateContactMenu();
        }
      }
      render();
    } catch (e) {
      toast(e.message);
    }
  }, 600);
}
async function setStage(st) {
  const targetHandle = S.sel;
  if (!targetHandle) return;
  const lead = leadOf(targetHandle);
  const prevStage = lead ? lead.stage : null;
  if (lead) lead.stage = st;
  if (S.ld && S.ld.lead) S.ld.lead.stage = st;
  if ($("#f-stage")) $("#f-stage").value = st;
  drawStrip();
  drawNext();
  render();

  try {
    await api(`${leadUrl(targetHandle)}/stage${bq()}`, {
      method: "PATCH",
      body: JSON.stringify({ stage: st }),
    });
    flashSaved();
  } catch (e) {
    if (lead && prevStage !== null) lead.stage = prevStage;
    if (S.ld && S.ld.lead && prevStage !== null) S.ld.lead.stage = prevStage;
    if ($("#f-stage") && prevStage !== null) $("#f-stage").value = prevStage;
    drawStrip();
    drawNext();
    render();
    toast(e.message);
  }
}
async function putLeadFor(h, extra = {}) {
  try {
    const d = await api(leadUrl(h) + bq());
    const l = d.lead;
    const body = {
      name: l.name || "",
      phone: l.phone || "",
      area: l.area || "",
      followers: l.followers || "",
      notes: l.notes || "",
      stage: l.stage || "new",
      follow_up: l.follow_up || "",
      price: l.price || "",
      ...extra,
    };
    await api(`${leadUrl(h)}${bq()}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    const local = leadOf(h);
    if (local) Object.assign(local, body);
    if (S.ld && S.sel === h) Object.assign(S.ld.lead, body);
    render();
    return true;
  } catch (e) {
    toast(e.message);
    return false;
  }
}
async function stageFor(h, st) {
  // used by drag & drop - instant optimistic UI update
  const lead = leadOf(h);
  const prevStage = lead ? lead.stage : null;
  if (lead) lead.stage = st;
  if (S.ld && S.sel === h && S.ld.lead) S.ld.lead.stage = st;
  render();

  try {
    await api(`${leadUrl(h)}/stage${bq()}`, {
      method: "PATCH",
      body: JSON.stringify({ stage: st }),
    });
    toast(`Moved to ${st}`);
  } catch (e) {
    if (lead && prevStage !== null) lead.stage = prevStage;
    if (S.ld && S.sel === h && S.ld.lead && prevStage !== null) S.ld.lead.stage = prevStage;
    render();
    toast(`Failed to move lead: ${e.message}`);
  }
}
function pitch(h) {
  const l = h ? leadOf(h) : (S.ld?.lead || leadOf(S.sel));
  const n = (l && l.name) || h || S.sel || "there";
  return `Hi ${n}, I came across your Instagram and made a website concept for your business. Would you like to take a look?`;
}
function whatsapp(h) {
  const l = h ? leadOf(h) : (S.ld?.lead || leadOf(S.sel));
  const rawPhone = (l && l.phone) || ($("#f-phone")?.value) || "";
  const p = rawPhone.replace(/\D/g, "");
  if (!p) {
    toast("No phone number on this lead");
    return false;
  }
  window.open(`https://wa.me/${p}?text=${enc(pitch(h))}`, "_blank");
  return true;
}

/* ---------- running ---------- */
async function saveAccounts(quiet) {
  const x = await api("/api/accounts", {
    method: "POST",
    body: JSON.stringify({
      text: $("#accounts").value,
      batch: $("#batch").value,
    }),
  });
  $("#accounts").value = x.handles.join("\n");
  if (!quiet) {
    await refresh(false);
    toast(`${x.handles.length} accounts saved`);
  }
  return x;
}
async function runBuild(
  handles = [],
  force = $("#force").checked,
  rescrape = $("#rescrape").checked,
  scrape_only = S.view === "batch" && $("#scrape-only").checked,
) {
  try {
    if (S.view === "batch" || !handles.length) await saveAccounts(true);
    const x = await api("/api/run" + bq(), {
      method: "POST",
      body: JSON.stringify({ handles, force, rescrape, scrape_only }),
    });
    toast(`Queued ${x.handles.length} profile(s)`);
    jobStatus();
  } catch (e) {
    toast(e.message);
  }
}

/* ---------- settings ---------- */
function fillSettings() {
  const s = S.st.settings || {};
  if (!s.websites_root && s.websites_root !== "" && !Object.keys(s).length)
    return;
  $("#sroot").value = s.websites_root || "";
  $("#sroot").dataset.filled = "1";
  $("#smodel").value = s.model || "";
  $("#stimeout").value = s.timeout ?? "";
  $("#sparallel").value = s.parallelism ?? "";
  $("#sposts").value = s.max_posts ?? "";
  $("#sattempts").value = s.attempts ?? "";
  $("#ssheet").value = s.sheet_name || "";
  $("#screds").value = s.credentials || "";
  $("#sbrowser").value = s.browser || "";
  $("#scaptions").checked = !!s.captions;
  $("#sheaded").checked = !!s.headed;
  $("#ssync").checked = !!s.sync_sheet;
  if ($("#slocalmode")) $("#slocalmode").checked = !!s.local_mode;
  drawSwatches();
  loadCredentialsIntoSettings();
}
async function saveSettings() {
  const timeout = parseInt($("#stimeout").value, 10);
  const parallelism = parseInt($("#sparallel").value, 10);
  const max_posts = parseInt($("#sposts").value, 10);
  const attempts = parseInt($("#sattempts").value, 10);
  if (!Number.isFinite(timeout) || timeout < 1) {
    toast("Timeout must be at least 1 second");
    return;
  }
  if (!Number.isFinite(parallelism) || parallelism < 1) {
    toast("Parallel builds must be at least 1");
    return;
  }
  if (!Number.isFinite(max_posts) || max_posts < 1) {
    toast("Maximum posts must be at least 1");
    return;
  }
  if (!Number.isFinite(attempts) || attempts < 1) {
    toast("Retry attempts must be at least 1");
    return;
  }
  const values = {
    websites_root: $("#sroot").value,
    model: $("#smodel").value,
    timeout,
    parallelism,
    max_posts,
    attempts,
    sheet_name: $("#ssheet").value,
    credentials: $("#screds").value,
    browser: $("#sbrowser").value,
    captions: $("#scaptions").checked,
    headed: $("#sheaded").checked,
    sync_sheet: $("#ssync").checked,
    local_mode: $("#slocalmode") ? $("#slocalmode").checked : false,
  };
  try {
    S.st.settings = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify({ values }),
    });
    toast("Settings saved");
    await refresh(false);
  } catch (e) {
    toast(e.message);
  }
}

async function loadCredentialsIntoSettings() {
  try {
    const c = await api("/api/credentials");
    if ($("#cf-account-id")) $("#cf-account-id").value = c.account_id || "";
    if ($("#cf-database-id")) $("#cf-database-id").value = c.database_id || "";
    if ($("#cf-team-member")) $("#cf-team-member").value = c.team_member_name || "";
    if ($("#cf-r2-bucket")) $("#cf-r2-bucket").value = c.r2_bucket_name || "";
    if ($("#cf-r2-access")) $("#cf-r2-access").value = c.r2_access_key || "";
    if ($("#cf-api-token") && c.has_api_token) $("#cf-api-token").placeholder = "•••••••• (Token saved)";
    if ($("#cf-r2-secret") && c.has_r2_secret) $("#cf-r2-secret").placeholder = "•••••••• (Secret saved)";
  } catch (e) {}
}

async function saveCredentials() {
  const btn = $("#btn-save-credentials");
  const origText = btn ? btn.textContent : "Test & Save";
  const msgEl = $("#cf-status-msg");
  if (msgEl) msgEl.hidden = true;
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Connecting to D1...";
  }
  try {
    const payload = {
      account_id: $("#cf-account-id").value.trim(),
      database_id: $("#cf-database-id").value.trim(),
      api_token: $("#cf-api-token").value.trim(),
      team_member_name: $("#cf-team-member").value.trim(),
      r2_bucket_name: $("#cf-r2-bucket").value.trim(),
      r2_access_key: $("#cf-r2-access").value.trim(),
      r2_secret_key: $("#cf-r2-secret").value.trim(),
    };
    if (!payload.account_id || !payload.database_id) {
      throw new Error("Cloudflare Account ID and D1 Database ID are required.");
    }
    const res = await api("/api/credentials", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    toast(res.message || "Connected to Cloudflare D1 successfully!");
    if (msgEl) {
      msgEl.textContent = res.message;
      msgEl.style.color = "var(--success)";
      msgEl.hidden = false;
    }
    await refresh(true);
  } catch (err) {
    if (msgEl) {
      msgEl.textContent = err.message || "Failed to connect to Cloudflare D1";
      msgEl.style.color = "var(--danger)";
      msgEl.hidden = false;
    }
    toast(err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = origText;
    }
  }
}

function openSetupModal() {
  const ov = $("#setupov");
  if (!ov) return;
  ov.hidden = false;
  api("/api/credentials")
    .then((c) => {
      if (c.account_id && $("#init-cf-account")) $("#init-cf-account").value = c.account_id;
      if (c.database_id && $("#init-cf-database")) $("#init-cf-database").value = c.database_id;
      if (c.team_member_name && $("#init-cf-name")) $("#init-cf-name").value = c.team_member_name;
      if (c.r2_bucket_name && $("#init-r2-bucket")) $("#init-r2-bucket").value = c.r2_bucket_name;
      if (c.r2_access_key && $("#init-r2-access")) $("#init-r2-access").value = c.r2_access_key;
    })
    .catch(() => {});
}

function closeSetupModal() {
  const ov = $("#setupov");
  if (ov) ov.hidden = true;
}

async function submitSetup() {
  const btn = $("#btn-submit-setup");
  const errEl = $("#setup-err-msg");
  if (errEl) errEl.hidden = true;
  const origText = btn ? btn.textContent : "Connect";
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Verifying D1...";
  }
  try {
    const payload = {
      account_id: $("#init-cf-account").value.trim(),
      database_id: $("#init-cf-database").value.trim(),
      api_token: $("#init-cf-token").value.trim(),
      team_member_name: $("#init-cf-name").value.trim(),
      r2_bucket_name: $("#init-r2-bucket").value.trim(),
      r2_access_key: $("#init-r2-access").value.trim(),
      r2_secret_key: $("#init-r2-secret").value.trim(),
    };
    if (!payload.account_id || !payload.database_id || !payload.api_token) {
      throw new Error("Please enter your Cloudflare Account ID, Database ID, and API Token.");
    }
    const res = await api("/api/credentials", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    toast(res.message || "Connected to Cloudflare D1 successfully!");
    closeSetupModal();
    await refresh(true);
  } catch (err) {
    if (errEl) {
      errEl.textContent = err.message || "Connection failed. Please check your credentials.";
      errEl.hidden = false;
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = origText;
    }
  }
}

async function enableOfflineMode() {
  const ok = await confirmDlg("Offline Mode", "Switch to offline mode? Lead data will be stored locally in SQLite.", "Use Offline Mode");
  if (ok) {
    try {
      await api("/api/settings", {
        method: "PUT",
        body: JSON.stringify({ values: { local_mode: true } }),
      });
      closeSetupModal();
      toast("Switched to offline local mode");
      await refresh(true);
    } catch (e) {
      toast(e.message);
    }
  }
}

/* ---------- present + recorder ---------- */
const P = {
  rec: null,
  chunks: [],
  timer: null,
  t0: 0,
  raf: 0,
  device: "desktop",
};
function openPresent(autoRecord) {
  if (!hasSite()) {
    toast("Build the site first");
    return;
  }
  $("#present").hidden = false;
  $("#pframe").src = previewUrl(S.sel);
  pdevice(P.device);
  if (autoRecord) {
    toast("Pick this tab in the share dialog, then recording starts");
    toggleRecord();
  }
}
function pdevice(d) {
  P.device = d;
  $("#pstage").className = "pstage " + (d === "desktop" ? "" : d);
  $$('#present [data-act="pdevice"]').forEach((b) =>
    b.classList.toggle("on", b.dataset.d === d),
  );
}
function exitPresent() {
  if (P.rec && P.rec.state === "recording") stopRecord();
  if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
  $("#present").hidden = true;
  $("#pframe").removeAttribute("src");
}
function fmt(ms) {
  const s = Math.floor(ms / 1000);
  return (
    String(Math.floor(s / 60)).padStart(2, "0") +
    ":" +
    String(s % 60).padStart(2, "0")
  );
}
async function toggleRecord() {
  if (P.rec && P.rec.state === "recording") {
    stopRecord();
    return;
  }
  const frame = $("#pframe");
  if (
    !("CropTarget" in window) ||
    typeof CropTarget.fromElement !== "function"
  ) {
    toast("Recording needs Chrome or Edge (region capture).");
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getDisplayMedia({
      video: {
        frameRate: 30,
        width: { ideal: 3840 },
        height: { ideal: 2160 },
      },
      audio: false,
      preferCurrentTab: true,
    });
  } catch (e) {
    toast("Screen capture cancelled");
    return;
  }
  const track = stream.getVideoTracks()[0];
  try {
    if (typeof track.cropTo !== "function") throw 0;
    await track.cropTo(await CropTarget.fromElement(frame));
  } catch {
    stream.getTracks().forEach((t) => t.stop());
    toast("Choose this tab in the share picker so the preview can be cropped.");
    return;
  }
  // countdown (not recorded: recorder has not started yet)
  const cd = $("#countdown");
  cd.hidden = false;
  for (let n = 3; n > 0; n--) {
    cd.textContent = n;
    await new Promise((r) => setTimeout(r, 900));
  }
  cd.hidden = true;
  try {
    frame.contentWindow.scrollTo(0, 0);
  } catch {}
  const mimeType = [
    "video/mp4;codecs=avc1.42E01E",
    "video/mp4",
    "video/webm;codecs=vp9",
    "video/webm;codecs=vp8",
    "video/webm",
  ].find((t) => MediaRecorder.isTypeSupported(t));
  const bps = +$("#pquality").value || 16000000;
  P.rec = new MediaRecorder(stream, {
    ...(mimeType ? { mimeType } : {}),
    videoBitsPerSecond: bps,
  });
  P.chunks = [];
  P.rec.ondataavailable = (e) => e.data.size && P.chunks.push(e.data);
  P.rec.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    cancelAnimationFrame(P.raf);
    clearInterval(P.timer);
    $("#rec").classList.remove("on");
    $("#p-rec").innerHTML = lab("rec", "Start recording");
    $("#p-rec").setAttribute("aria-label", "Start recording");
    const type = P.rec.mimeType || "video/webm";
    const ext = type.includes("mp4") ? "mp4" : "webm";
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(P.chunks, { type }));
    a.download = `${S.sel || "site"}-${P.device}.${ext}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    setSyncIndicator(`Uploading ${P.device} recording…`);
    try {
      const blob = new Blob(P.chunks, { type });
      const qs = new URLSearchParams({
        batch: S.st.batch,
        screen: P.device,
        extension: ext,
      });
      const res = await api(`${leadUrl(S.sel)}/recording?${qs}`, {
        method: "POST",
        body: blob,
      });
      setSyncIndicator(null);
      if (res && res.r2_url) {
        toast(`Recording uploaded & synced to Cloudflare R2!`);
      } else {
        toast(`Recording saved as ${S.sel}-${P.device}.${ext}`);
      }
      const st = stageOf(S.ld?.lead || {});
      if (st === "new" || st === "built") await setStage("recorded");
    } catch (e) {
      setSyncIndicator(null);
      toast(`Download saved; server upload failed: ${e.message}`);
    }
    if (S.sel) loadLead(S.sel, true);
  };
  P.rec.start(1000);
  P.t0 = Date.now();
  $("#rec").classList.add("on");
  $("#p-rec").innerHTML = lab("stop", "Stop recording");
  $("#p-rec").setAttribute("aria-label", "Stop recording");
  P.timer = setInterval(
    () => ($("#rectime").textContent = fmt(Date.now() - P.t0)),
    250,
  );
  if ($("#pauto").checked) autoScroll(frame);
}
function autoScroll(frame) {
  try {
    if (frame && frame.contentWindow) {
      frame.contentWindow.postMessage({ action: "autoScroll" }, "*");
    }
  } catch {
    toast("Auto-scroll unavailable for this page; scroll manually");
  }
}
window.addEventListener("message", (e) => {
  if (e.data && e.data.action === "scrollDone") {
    if (P.rec && P.rec.state === "recording") stopRecord();
  }
});
function stopRecord() {
  if (P.rec && P.rec.state === "recording") P.rec.stop();
}

/* ---------- cinema video player ---------- */
const V = {
  handle: null,
  screen: "desktop",
  recordings: {},
};

function showVideoPlaceholder(screen) {
  const ph = $("#v-placeholder");
  const player = $("#v-player");
  if (player) player.classList.remove("v-ready");
  if (!ph) return;
  ph.classList.remove("v-hidden");
  const s = screen || "desktop";
  const name = s.charAt(0).toUpperCase() + s.slice(1);
  const iconName = s === "desktop" ? "monitor" : s;
  if ($("#v-ph-icon")) $("#v-ph-icon").innerHTML = ic(iconName, 26);
  if ($("#v-ph-title"))
    $("#v-ph-title").textContent = `Loading ${name} recording…`;
  if ($("#v-ph-sub")) $("#v-ph-sub").textContent = "Preparing video stream…";
  const bar = $(".v-placeholder-bar", ph);
  if (bar) bar.hidden = false;
}

function hideVideoPlaceholder() {
  const ph = $("#v-placeholder");
  const player = $("#v-player");
  if (player) player.classList.add("v-ready");
  if (ph) ph.classList.add("v-hidden");
}

function showVideoError(msg) {
  const ph = $("#v-placeholder");
  const player = $("#v-player");
  if (player) player.classList.remove("v-ready");
  if (!ph) return;
  ph.classList.remove("v-hidden");
  if ($("#v-ph-icon")) $("#v-ph-icon").innerHTML = ic("trash", 24);
  if ($("#v-ph-title")) $("#v-ph-title").textContent = "Recording not ready";
  if ($("#v-ph-sub"))
    $("#v-ph-sub").textContent =
      msg || "Video stream is currently unavailable.";
  const bar = $(".v-placeholder-bar", ph);
  if (bar) bar.hidden = true;
}

const vpInit = $("#v-player");
if (vpInit) {
  const handleReady = () => {
    hideVideoPlaceholder();
    if (vpInit.videoWidth && vpInit.videoHeight) {
      const dialog = $(".video-dialog");
      if (dialog && !dialog.getAttribute("data-screen")) {
        const isPortrait = vpInit.videoHeight > vpInit.videoWidth;
        dialog.setAttribute("data-screen", isPortrait ? "phone" : "desktop");
      }
    }
  };
  vpInit.addEventListener("loadedmetadata", handleReady);
  vpInit.addEventListener("loadeddata", handleReady);
  vpInit.addEventListener("canplay", handleReady);
  vpInit.addEventListener("playing", hideVideoPlaceholder);
  vpInit.addEventListener("error", () => {
    showVideoError("Could not load recording from server.");
  });
}

async function openVideoPlayer(handle, preferredDevice) {
  if (!handle) return;
  V.handle = handle;
  $("#v-title").textContent = `@${handle}`;
  $("#videomodal").hidden = false;
  document.body.style.overflow = "hidden";

  try {
    if (S.ld && S.ld.lead && S.ld.lead.handle === handle && S.ld.recordings) {
      V.recordings = S.ld.recordings;
    } else {
      const data = await api(leadUrl(handle) + bq());
      V.recordings = data.recordings || {};
    }
  } catch {
    V.recordings = {};
  }

  const screens = ["desktop", "tablet", "phone"].filter((s) => V.recordings[s]);
  const availableScreens = screens.length ? screens : ["desktop"];
  if (preferredDevice && availableScreens.includes(preferredDevice)) {
    V.screen = preferredDevice;
  } else if (availableScreens.includes("desktop")) {
    V.screen = "desktop";
  } else {
    V.screen = availableScreens[0];
  }

  const tabs = $("#v-tabs");
  tabs.innerHTML =
    availableScreens.length > 1
      ? availableScreens
          .map(
            (s) =>
              `<button class="video-tab ${s === V.screen ? "active" : ""}" data-act="switchVideoScreen" data-s="${s}">${ic(s === "desktop" ? "monitor" : s, 13)} <span>${s.charAt(0).toUpperCase() + s.slice(1)}</span></button>`,
          )
          .join("")
      : "";

  loadVideoScreen(V.screen);
}
function resetDelConfirm() {
  const btn = $("#v-del-btn");
  const box = $("#v-del-confirm");
  if (btn) btn.hidden = false;
  if (box) box.hidden = true;
}
function askDelConfirm() {
  const btn = $("#v-del-btn");
  const box = $("#v-del-confirm");
  const targetEl = $("#v-del-target");
  if (!btn || !box) return;
  const devName = V.screen.charAt(0).toUpperCase() + V.screen.slice(1);
  if (targetEl) targetEl.textContent = devName;
  btn.hidden = true;
  box.hidden = false;
}
function loadVideoScreen(screen) {
  V.screen = screen;
  const dialog = $(".video-dialog");
  if (dialog) dialog.setAttribute("data-screen", screen);
  resetDelConfirm();
  $$("#v-tabs .video-tab").forEach((b) =>
    b.classList.toggle("active", b.dataset.s === screen),
  );
  const name = screen.charAt(0).toUpperCase() + screen.slice(1);
  $("#v-meta").textContent = `${name} demo recording`;
  showVideoPlaceholder(screen);
  const player = $("#v-player");
  player.src = `${leadUrl(V.handle)}/recording/${screen}?${bq().slice(1)}`;
  player.play().catch(() => {});
}
function switchVideoScreen(screen) {
  if (V.screen === screen) return;
  loadVideoScreen(screen);
}
function closeVideoPlayer() {
  resetDelConfirm();
  const player = $("#v-player");
  player.pause();
  player.removeAttribute("src");
  player.load();
  player.classList.remove("v-ready");
  const dialog = $(".video-dialog");
  if (dialog) dialog.removeAttribute("data-screen");
  showVideoPlaceholder(V.screen);
  $("#videomodal").hidden = true;
  if ($("#studio").hidden && $("#present").hidden) {
    document.body.style.overflow = "";
  }
}
function downloadCurrentVideo() {
  if (!V.handle) return;
  const a = document.createElement("a");
  a.href = `${leadUrl(V.handle)}/recording/${V.screen}?download=true&${bq().slice(1)}`;
  a.click();
}
async function executeDeleteCurrentVideo() {
  if (!V.handle || !V.screen) return;
  const screenToDelete = V.screen;
  const devName =
    screenToDelete.charAt(0).toUpperCase() + screenToDelete.slice(1);
  resetDelConfirm();
  setSyncIndicator(`Deleting ${devName} recording…`);
  try {
    const res = await api(
      `${leadUrl(V.handle)}/recording/${screenToDelete}?${bq().slice(1)}`,
      { method: "DELETE" },
    );
    toast(`${devName} recording deleted`);

    V.recordings = res.remaining || {};
    const remainingScreens = ["desktop", "tablet", "phone"].filter(
      (s) => V.recordings[s],
    );

    if (remainingScreens.length > 0) {
      const nextScreen = remainingScreens.includes("desktop")
        ? "desktop"
        : remainingScreens[0];
      const tabs = $("#v-tabs");
      tabs.innerHTML =
        remainingScreens.length > 1
          ? remainingScreens
              .map(
                (s) =>
                  `<button class="video-tab ${s === nextScreen ? "active" : ""}" data-act="switchVideoScreen" data-s="${s}">${ic(s === "desktop" ? "monitor" : s, 13)} <span>${s.charAt(0).toUpperCase() + s.slice(1)}</span></button>`,
              )
              .join("")
          : "";
      loadVideoScreen(nextScreen);
    } else {
      closeVideoPlayer();
    }

    if (S.sel === V.handle) {
      await loadLead(V.handle, true);
    }
    await refresh(false);
  } catch (e) {
    toast(`Failed to delete recording: ${e.message}`);
  } finally {
    setSyncIndicator(null);
  }
}

/* ---------- command palette ---------- */
let palItems = [],
  palIdx = 0;
function commands() {
  const c = [
    {
      t: "Go to Pipeline",
      k: "view",
      run: () => {
        closeStudio();
        setView("pipeline");
      },
    },
    {
      t: "Go to Batch",
      run: () => {
        closeStudio();
        setView("batch");
      },
    },
    {
      t: "Open Settings",
      run: () => {
        closeStudio();
        setView("settings");
      },
    },
    { t: "Run batch", run: () => runBuild() },
    {
      t: "Toggle light / dark theme",
      run: () =>
        setTheme(
          document.documentElement.dataset.theme === "light" ? "dark" : "light",
        ),
    },
    {
      t: "Switch to " + (S.layout === "board" ? "list" : "board") + " layout",
      run: () => {
        S.layout = S.layout === "board" ? "list" : "board";
        localStorage.setItem("studio-layout", S.layout);
        render();
      },
    },
    {
      t: "Export leads CSV",
      run: () => (location.href = "/api/leads.csv" + bq()),
    },
  ];
  if (!$("#studio").hidden && S.sel) {
    c.push(
      { t: "Rebuild this site", run: () => runBuild([S.sel], true) },
      { t: "Present mode", run: () => openPresent() },
      {
        t: "Copy pitch",
        run: () =>
          navigator.clipboard
            .writeText(pitch())
            .then(() => toast("Pitch copied")),
      },
      {
        t: "Open Instagram profile",
        run: () => window.open(`https://www.instagram.com/${S.sel}/`, "_blank"),
      },
      {
        t: "Download ZIP",
        run: () => (location.href = `${leadUrl(S.sel)}/zip${bq()}`),
      },
    );
  }
  return c;
}
function openPalette() {
  $("#paletteov").hidden = false;
  $("#palq").value = "";
  drawPalette();
  $("#palq").focus();
}
function drawPalette() {
  const q = $("#palq").value.toLowerCase();
  const leads = (S.st.leads || []).map((l) => ({
    t: l.name || "@" + l.handle,
    sub: "@" + l.handle,
    run: () => {
      if ($("#studio").hidden) openStudio(l.handle);
      else {
        S.sel = l.handle;
        openStudio(l.handle);
      }
    },
  }));
  palItems = [...commands(), ...leads]
    .filter((i) => !q || (i.t + " " + (i.sub || "")).toLowerCase().includes(q))
    .slice(0, 40);
  palIdx = Math.min(palIdx, Math.max(0, palItems.length - 1));
  $("#pallist").innerHTML =
    palItems
      .map(
        (i, n) =>
          `<li class="${n === palIdx ? "on" : ""}" data-n="${n}">${esc(i.t)}<small>${esc(i.sub || "")}</small></li>`,
      )
      .join("") || '<li class="muted">No matches</li>';
}
function runPal(n) {
  const i = palItems[n];
  if (!i) return;
  $("#paletteov").hidden = true;
  i.run();
}

/* ---------- actions ---------- */
const A = {
  logout: () => logout(),
  view: (el) => {
    closeStudioIfOpen();
    setView(el.dataset.v);
  },
  theme: () =>
    setTheme(
      document.documentElement.dataset.theme === "light" ? "dark" : "light",
    ),
  "palette-set": (el) => setPalette(el.dataset.p),
  palette: openPalette,
  filter: (el) => {
    S.filter = el.dataset.f;
    render();
  },
  layout: (el) => {
    S.layout = el.dataset.l;
    localStorage.setItem("studio-layout", S.layout);
    render();
  },
  selmode: () => {
    S.selmode = !S.selmode;
    if (!S.selmode) S.checked.clear();
    render();
  },
  check: (el, e) => {
    e.stopPropagation();
    el.checked ? S.checked.add(el.dataset.h) : S.checked.delete(el.dataset.h);
    el.closest(".card")?.classList.toggle("picked", el.checked);
    renderSelbar();
  },
  open: (el) => {
    if (S.selmode) {
      const h = el.dataset.h;
      S.checked.has(h) ? S.checked.delete(h) : S.checked.add(h);
      render();
      return;
    }
    openStudio(el.dataset.h);
  },
  openPreviewTab: (el, e) => {
    e.stopPropagation();
    const h = el.dataset.h;
    if (h) window.open(previewUrl(h), "_blank");
  },
  cardWa: (el, e) => {
    e.stopPropagation();
    const h = el.dataset.h;
    if (h) whatsapp(h);
  },
  cardMarkWon: async (el, e) => {
    e.stopPropagation();
    const h = el.dataset.h;
    const cur = leadOf(h).price || "$499";
    const p = prompt(`Enter quoted deal value for @${h}:`, cur);
    if (p !== null) {
      await putLeadFor(h, { stage: "won", price: p });
      toast(`@${h} marked as Won! Moved to Clients.`);
      await refresh(false);
    }
  },
  cardMarkLost: async (el, e) => {
    e.stopPropagation();
    const h = el.dataset.h;
    if (
      await confirmDlg(
        "Archive Lead",
        `Move @${h} to Lost / Archive?`,
        "Archive",
      )
    ) {
      await api(`/api/lead/${enc(h)}/archive${bq()}`, { method: "POST" });
      toast(`@${h} moved to Lost.`);
      await refresh(false);
    }
  },
  studioWon: async () => {
    const h = S.sel;
    if (!h) return;
    const cur = $("#f-price")?.value || leadOf(h).price || "$499";
    const p = prompt(`Enter quoted deal value for @${h}:`, cur);
    if (p !== null) {
      if ($("#f-price")) $("#f-price").value = p;
      await putLead({ stage: "won", price: p });
      toast(`@${h} marked as Won! Moved to Clients.`);
      await refresh(false);
      closeStudio();
      setView("clients");
    }
  },
  reopenLead: async (el, e) => {
    e.stopPropagation();
    const h = el.dataset.h;
    if (h) {
      await putLeadFor(h, { stage: "replied" });
      toast(`Reopened @${h} to Replied.`);
      await refresh(false);
    }
  },
  cardMenu: (el, e) => {
    e.stopPropagation();
    const h = el.dataset.h;
    const m = $(`#cardmenu-${h}`);
    if (!m) return;
    const isHidden = m.hidden;
    $$(".card-menulist").forEach((x) => (x.hidden = true));
    m.hidden = !isHidden;
  },
  cardCopyPitch: (el, e) => {
    e.stopPropagation();
    const h = el.dataset.h;
    $$(".card-menulist").forEach((x) => (x.hidden = true));
    navigator.clipboard.writeText(pitch(h)).then(() => toast("Pitch copied"));
  },
  cardRebuild: (el, e) => {
    e.stopPropagation();
    const h = el.dataset.h;
    $$(".card-menulist").forEach((x) => (x.hidden = true));
    runBuild([h], true);
  },
  cardZip: (el, e) => {
    e.stopPropagation();
    const h = el.dataset.h;
    $$(".card-menulist").forEach((x) => (x.hidden = true));
    const a = document.createElement("a");
    a.href = `${leadUrl(h)}/zip?mode=site&${bq().slice(1)}`;
    a.download = `${h}-site.zip`;
    a.click();
    toast(`Downloading ${h}-site.zip…`);
  },
  retry: (el, e) => {
    e.stopPropagation();
    runBuild([el.dataset.h], true);
  },
  runChecked: () => runBuild([...S.checked]),
  deleteChecked: () => chooseDelete([...S.checked]),
  deleteOne: () => {
    $("#smenu").hidden = true;
    chooseDelete([S.sel]);
  },
  run: () => runBuild(),
  saveAccounts: () => saveAccounts().catch((e) => toast(e.message)),
  cancel: async () => {
    await api("/api/cancel", { method: "POST" });
    toast("Cancellation requested");
  },
  importPick: () => $("#importfile").click(),
  exportAccounts: () => (location.href = "/api/accounts/export"),
  exportCsv: () => (location.href = "/api/leads.csv" + bq()),
  clearLogs: () => ($("#logs").innerHTML = ""),
  logZoom: (el) => {
    S.logZoom =
      el.dataset.d === "0"
        ? 11
        : Math.max(8, Math.min(24, S.logZoom + Number(el.dataset.d)));
    [$("#logs"), $("#revisionlogs")].forEach(
      (box) => (box.style.fontSize = `${S.logZoom}px`),
    );
  },
  saveSettings,
  saveCredentials,
  syncD1: async () => {
    try {
      toast("Syncing local changes to Cloudflare D1…");
      const res = await api("/api/sync/d1", { method: "POST" });
      toast(`Synced ${res.synced || 0} item(s) to Cloudflare D1!`);
      await refresh(false);
    } catch (e) {
      toast("Sync failed: " + e.message);
    }
  },
  login: async () => {
    try {
      await api("/api/auth/login", { method: "POST" });
      toast("Browser opened. Sign in to Instagram there.");
    } catch (e) {
      toast(e.message);
    }
  },
  clearAuth: async () => {
    try {
      await api("/api/auth/clear", { method: "POST" });
      await refresh(false);
      toast("Session cleared");
    } catch (e) {
      toast(e.message);
    }
  },
  health: async () => {
    try {
      const h = await api("/api/health");
      $("#healthresult").textContent = Object.entries(h.checks)
        .map(
          ([k, v]) =>
            k +
            ": " +
            (v
              ? "OK" +
                (k === "agy" && h.paths?.agy ? " (" + h.paths.agy + ")" : "")
              : "missing"),
        )
        .join(" · ");
    } catch (e) {
      $("#healthresult").textContent = e.message;
    }
  },
  sheetTest: async () => {
    try {
      const x = await api("/api/sheets/test", { method: "POST" });
      $("#healthresult").textContent = x.message;
      toast(x.message);
    } catch (e) {
      $("#healthresult").textContent = e.message;
      toast(e.message);
    }
  },
  closeStudio,
  menu: (el, e) => {
    e.stopPropagation();
    $("#smenu").hidden = !$("#smenu").hidden;
  },
  rebuild: () => {
    $("#smenu").hidden = true;
    runBuild([S.sel], true);
  },
  openTab: () => {
    $("#smenu").hidden = true;
    if (S.sel) window.open(previewUrl(S.sel), "_blank");
  },
  instagram: () => {
    $("#smenu").hidden = true;
    api(`/api/open/${enc(S.sel)}`).catch(() => {});
    window.open(`https://www.instagram.com/${S.sel}/`, "_blank");
  },
  whatsapp: () => {
    $("#smenu").hidden = true;
    whatsapp();
  },
  copyPitch: () => {
    $("#smenu").hidden = true;
    navigator.clipboard.writeText(pitch()).then(() => toast("Pitch copied"));
  },
  copyPath: () => {
    $("#smenu").hidden = true;
    S.ld?.lead.site_path &&
      navigator.clipboard
        .writeText(S.ld.lead.site_path)
        .then(() => toast("Path copied"));
  },
  zipSite: () => {
    $("#smenu").hidden = true;
    if (!S.sel) return;
    setSyncIndicator(`Preparing Website ZIP for @${S.sel}…`);
    toast("Preparing Website ZIP…");
    const a = document.createElement("a");
    a.href = `${leadUrl(S.sel)}/zip?mode=site&${bq().slice(1)}`;
    a.download = `${S.sel}-site.zip`;
    a.click();
    setTimeout(() => setSyncIndicator(null), 2500);
  },
  zipFull: () => {
    $("#smenu").hidden = true;
    if (!S.sel) return;
    setSyncIndicator(`Bundling Full Folder Archive for @${S.sel}…`);
    toast("Preparing Full Folder Archive ZIP…");
    const a = document.createElement("a");
    a.href = `${leadUrl(S.sel)}/zip?mode=full&${bq().slice(1)}`;
    a.download = `${S.sel}-full.zip`;
    a.click();
    setTimeout(() => setSyncIndicator(null), 3500);
  },
  downloadRec: () => {
    $("#smenu").hidden = true;
    if (!S.sel) return;
    const recs = S.ld?.recordings || {};
    const availableScreens = Object.keys(recs);
    let dev = S.device || P.device || "desktop";
    if (!availableScreens.includes(dev) && availableScreens.length > 0) {
      dev = availableScreens[0];
    }
    setSyncIndicator(`Downloading demo recording for @${S.sel}…`);
    toast(`Downloading ${dev} demo recording…`);
    const a = document.createElement("a");
    a.href = `${leadUrl(S.sel)}/recording/${dev}?download=true&${bq().slice(1)}`;
    a.download = `${S.sel}-${dev}.webm`;
    a.click();
    setTimeout(() => setSyncIndicator(null), 2500);
  },
  deleteRec: async () => {
    $("#smenu").hidden = true;
    if (!S.sel || !S.ld) return;
    const recs = S.ld.recordings || {};
    const devKeys = Object.keys(recs);
    if (!devKeys.length) return;

    let targetScreen = "all";
    if (devKeys.length === 1) {
      const s = devKeys[0];
      const name = s.charAt(0).toUpperCase() + s.slice(1);
      const ok = await confirmDlg(
        "Delete Recording",
        `Are you sure you want to delete the ${name} recording for @${S.sel}?`,
        "Delete",
      );
      if (!ok) return;
      targetScreen = s;
    } else {
      const options = [
        { label: "Cancel", value: null },
        ...devKeys.map((k) => ({
          label: `${k.charAt(0).toUpperCase() + k.slice(1)} only`,
          value: k,
          cls: "danger",
        })),
        { label: "All recordings", value: "all", cls: "danger" },
      ];
      const choice = await dlg(
        "Delete Recording",
        `Choose which recording to delete for @${S.sel}:`,
        options,
      );
      if (!choice) return;
      targetScreen = choice;
    }

    setSyncIndicator(`Deleting recording for @${S.sel}…`);
    try {
      const recordingUrl =
        targetScreen === "all"
          ? `${leadUrl(S.sel)}/recording${bq()}`
          : `${leadUrl(S.sel)}/recording/${targetScreen}${bq()}`;
      await api(recordingUrl, { method: "DELETE" });
      toast("Recording deleted");
      await loadLead(S.sel, true);
      await refresh(false);
    } catch (e) {
      toast(`Failed to delete recording: ${e.message}`);
    } finally {
      setSyncIndicator(null);
    }
  },
  device: (el) => {
    const d = el.dataset.d;
    S.device = d;
    $("#device").className = "device" + (d === "desktop" ? "" : " " + d);
    $$('[data-act="device"]').forEach((b) =>
      b.classList.toggle("on", b.dataset.d === d),
    );
  },
  reloadPreview: () => {
    bumpNonce(S.sel);
    if (S.sel && hasSite()) {
      const f = $("#preview");
      const ldr = $("#deviceloader");
      if (ldr) {
        ldr.classList.remove("fade-out");
        ldr.hidden = false;
        $("#loaderstatus").textContent = "Checking R2 for revisions…";
        $("#loadersub").textContent = "Syncing latest website files";
        f.onload = () => {
          ldr.classList.add("fade-out");
          setTimeout(() => {
            if (S.sel) ldr.hidden = true;
          }, 250);
        };
      }
      setSyncIndicator(`Checking @${S.sel} on R2…`);
      f.src = previewUrl(S.sel);
      setTimeout(() => setSyncIndicator(null), 1800);
    }
  },
  toggleSide: () => {
    S.sideOpen = !S.sideOpen;
    $("#sbody").classList.toggle("noside", !S.sideOpen);
  },
  tab: (el) => {
    $$(".tabs button").forEach((b) => b.classList.toggle("on", b === el));
    ["details", "photos", "revisions", "design"].forEach(
      (t) => ($("#pane-" + t).hidden = t !== el.dataset.t),
    );
  },
  setstage: (el) => setStage(el.dataset.s),
  next: async () => {
    if (!S.ld) return;
    const st = stageOf(S.ld.lead);
    if (!hasSite()) return runBuild([S.sel], true);
    if (st === "new" || st === "built") return openPresent(true);
    if (st === "recorded") {
      await navigator.clipboard.writeText(pitch()).catch(() => {});
      if (hasPhone()) whatsapp();
      else window.open(`https://www.instagram.com/${S.sel}/`, "_blank");
      await setStage("sent");
      toast("Pitch copied · marked as sent");
      return;
    }
    if (st === "sent") return setStage("replied");
    if (st === "replied") return setStage("won");
  },
  present: () => openPresent(),
  exitPresent,
  pdevice: (el) => pdevice(el.dataset.d),
  fullscreen: () => {
    const p = $("#present");
    document.fullscreenElement
      ? document.exitFullscreen()
      : p.requestFullscreen?.().catch(() => toast("Fullscreen blocked"));
  },
  record: toggleRecord,
  photo: (el) => {
    el.classList.toggle("on");
    updatePhotoCount();
    savePhotos();
  },
  addRevision: async () => {
    const text = $("#revision").value.trim();
    if (!text) return toast("Describe the change first");
    try {
      const r = await api(`/api/revision/${enc(S.sel)}${bq()}`, {
        method: "POST",
        body: JSON.stringify({ request: text }),
      });
      $("#revision").value = "";
      const queued = await api(
        `/api/revision/${enc(S.sel)}/${r.id}/apply${bq()}`,
        {
          method: "POST",
        },
      );
      toast(
        queued.queued
          ? `Revision queued · position ${queued.position}`
          : "Revision started",
      );
      bumpNonce(S.sel);
      loadLead(S.sel, false);
    } catch (e) {
      toast(e.message);
    }
  },
  reapply: async (el) => {
    try {
      const queued = await api(
        `/api/revision/${enc(S.sel)}/${el.dataset.id}/apply${bq()}`,
        { method: "POST" },
      );
      toast(
        queued.queued
          ? `Revision queued · position ${queued.position}`
          : "Revision started",
      );
    } catch (e) {
      toast(e.message);
    }
  },
  undorev: async (el) => {
    if (
      !(await confirmDlg(
        "Undo revision",
        "Restore the site backup made before this revision?",
        "Restore",
      ))
    )
      return;
    try {
      await api(`/api/revision/${enc(S.sel)}/${el.dataset.id}/undo${bq()}`, {
        method: "POST",
      });
      bumpNonce(S.sel);
      await loadLead(S.sel, true);
      toast("Backup restored");
    } catch (e) {
      toast(e.message);
    }
  },
  playRecording: () => {
    if (S.sel) openVideoPlayer(S.sel, S.device);
  },
  playCardRec: (el, e) => {
    if (e) {
      e.stopPropagation();
      e.preventDefault();
    }
    openVideoPlayer(el.dataset.h);
  },
  switchVideoScreen: (el) => {
    switchVideoScreen(el.dataset.s);
  },
  closeVideo: () => {
    closeVideoPlayer();
  },
  delAsk: (el, e) => {
    if (e) e.stopPropagation();
    askDelConfirm();
  },
  delConfirm: (el, e) => {
    if (e) e.stopPropagation();
    executeDeleteCurrentVideo();
  },
  delCancel: (el, e) => {
    if (e) e.stopPropagation();
    resetDelConfirm();
  },
  downloadVideo: () => {
    downloadCurrentVideo();
  },
  unlockLead: async () => {
    $("#smenu").hidden = true;
    if (!S.sel) return;
    try {
      await api(`${leadUrl(S.sel)}/unlock${bq()}`, { method: "POST" });
      toast(`Lead @${S.sel} unlocked`);
      await refresh(false);
    } catch (e) {
      toast("Unlock failed: " + e.message);
    }
  },
  archiveLead: async () => {
    $("#smenu").hidden = true;
    if (!S.sel) return;
    const ok = await confirmDlg(
      "Archive Lead",
      `Archive @${S.sel}? This moves stage to 'lost' and deletes website mockup assets.`,
      "Archive",
    );
    if (!ok) return;
    try {
      await api(`${leadUrl(S.sel)}/archive${bq()}`, { method: "POST" });
      toast(`Lead @${S.sel} archived`);
      closeStudio();
      await refresh(false);
    } catch (e) {
      toast("Archive failed: " + e.message);
    }
  },
  pingServer: async () => {
    try {
      const res = await api("/api/ping");
      toast(`Server connection OK (${res.status})`);
    } catch (e) {
      toast("Server ping failed: " + e.message);
    }
  },
};
function closeStudioIfOpen() {
  if (!$("#studio").hidden) closeStudio();
}
async function chooseDelete(handles) {
  if (!handles.length) return;
  const names = handles.map((h) => "@" + h).join(", ");
  const mode = await dlg(
    "Delete " + (handles.length > 1 ? handles.length + " leads" : "lead"),
    `Choose what to remove for ${names}. “Website only” keeps scraped Instagram data and backups. “Everything” removes those too. Both remove the lead and its revision history from the database.`,
    [
      { label: "Cancel", value: null },
      { label: "Website only", value: "site", cls: "danger" },
      { label: "Everything", value: "folder", cls: "danger" },
    ],
  );
  if (!mode) return;
  try {
    await api("/api/lead/delete" + bq(), {
      method: "POST",
      body: JSON.stringify({ handles, mode }),
    });
    handles.forEach((h) => S.checked.delete(h));
    if (handles.includes(S.sel)) {
      S.sel = "";
      S.ld = null;
      $("#studio").hidden = true;
      document.body.style.overflow = "";
    }
    await refresh(false);
    toast(
      mode === "site"
        ? "Lead removed, website deleted"
        : "Lead and entire folder deleted",
    );
  } catch (e) {
    toast(e.message);
  }
}

/* ---------- events ---------- */
document.addEventListener("click", (e) => {
  if (justDragged) {
    justDragged = false;
    return;
  }
  if (!e.target.closest(".menu")) {
    $("#smenu").hidden = true;
    $$(".card-menulist").forEach((m) => (m.hidden = true));
  }
  if (!e.target.closest("#v-del-wrap")) resetDelConfirm();
  const el = e.target.closest("[data-act]");
  if (el && A[el.dataset.act]) {
    if (el.matches(".card") && e.target.closest(".card-actions")) {
      return;
    }
    if (el.type === "checkbox") {
      A[el.dataset.act](el, e);
      return;
    }
    A[el.dataset.act](el, e);
  }
  const li = e.target.closest("#pallist li[data-n]");
  if (li) runPal(+li.dataset.n);
  if (e.target === $("#paletteov")) $("#paletteov").hidden = true;
});
document.addEventListener("keydown", async (e) => {
  const typing = /INPUT|TEXTAREA|SELECT/.test(e.target.tagName);
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
    e.preventDefault();
    $("#paletteov").hidden ? openPalette() : ($("#paletteov").hidden = true);
    return;
  }
  if (!$("#paletteov").hidden) {
    if (e.key === "Escape") $("#paletteov").hidden = true;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      palIdx = Math.min(palIdx + 1, palItems.length - 1);
      drawPalette();
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      palIdx = Math.max(palIdx - 1, 0);
      drawPalette();
    }
    if (e.key === "Enter") runPal(palIdx);
    return;
  }
  if (!$("#dlgov").hidden) {
    if (e.key === "Escape") {
      $("#dlgov").hidden = true;
      if (dlgRes) {
        const r = dlgRes;
        dlgRes = null;
        r(false);
      }
    }
    return;
  }
  if (!$("#videomodal").hidden) {
    if (e.key === "Escape") {
      e.preventDefault();
      closeVideoPlayer();
      return;
    }
    if (e.key === " " || e.code === "Space") {
      if (!typing) {
        e.preventDefault();
        const vp = $("#v-player");
        if (vp.paused) vp.play();
        else vp.pause();
        return;
      }
    }
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      const vp = $("#v-player");
      vp.currentTime = Math.max(0, vp.currentTime - 5);
      return;
    }
    if (e.key === "ArrowRight") {
      e.preventDefault();
      const vp = $("#v-player");
      vp.currentTime = Math.min(vp.duration || 0, vp.currentTime + 5);
      return;
    }
    if (e.key.toLowerCase() === "f" && !typing) {
      e.preventDefault();
      const vp = $("#v-player");
      if (document.fullscreenElement) {
        document.exitFullscreen().catch(() => {});
      } else if (vp.requestFullscreen) {
        vp.requestFullscreen().catch(() => {});
      }
      return;
    }
    if (e.key.toLowerCase() === "m" && !typing) {
      e.preventDefault();
      const vp = $("#v-player");
      vp.muted = !vp.muted;
      return;
    }
    return;
  }
  if (e.key === "Escape") {
    if (!$("#present").hidden) {
      exitPresent();
      return;
    }
    if (!$("#studio").hidden) {
      closeStudio();
      return;
    }
    if (S.selmode) A.selmode();
    return;
  }
  if (!$("#present").hidden && e.key.toLowerCase() === "r" && !typing) {
    toggleRecord();
    return;
  }
  if (typing) {
    if (e.key === "Enter" && e.altKey && e.target.id === "revision")
      A.addRevision();
    return;
  }
  if (!$("#studio").hidden) {
    const k = e.key.toLowerCase();
    if (k === "r") {
      if (
        e.shiftKey ||
        (await confirmDlg(
          "Rebuild Site",
          `Rebuild website mockup for @${S.sel}?`,
          "Rebuild",
        ))
      ) {
        runBuild([S.sel], true);
      }
    }
    if (k === "p") openPresent();
    if (k === "j" || k === "k") {
      const list = filtered();
      const i = list.findIndex((x) => x.handle === S.sel);
      const n = list[i + (k === "j" ? 1 : -1)];
      if (n) {
        S.sel = n.handle;
        openStudio(n.handle);
      }
    }
  }
});
$("#palq").addEventListener("input", () => {
  palIdx = 0;
  drawPalette();
});
$("#q").addEventListener("input", render);
$("#q-clients")?.addEventListener("input", renderClients);
$("#batch").addEventListener("change", async () => {
  const b = $("#batch").value;
  S.sel = "";
  S.checked.clear();
  S.loadingBatch = true;
  setSyncIndicator(`Loading batch ${b}…`);
  const root = $("#pipeline");
  if (root && S.view === "pipeline") {
    root.innerHTML = `<div class="empty" style="padding: 70px 16px;">
            <div class="loader-spinner" style="margin: 0 auto 16px;"></div>
            <h3 style="font-size: 16px; margin-bottom: 6px; color: var(--text);">Loading batch ${esc(b)}…</h3>
            <div class="muted" style="font-size: 13px;">Pulling leads and mockups from database</div>
          </div>`;
  }
  $("#batch").disabled = true;
  try {
    await refresh(false);
  } finally {
    $("#batch").disabled = false;
    setSyncIndicator(null);
  }
});
$("#importfile").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (f) $("#accounts").value = await f.text();
  e.target.value = "";
});
document.addEventListener("input", (e) => {
  if (e.target.matches("[data-field]")) autosave();
});
document.addEventListener("change", (e) => {
  if (e.target.matches("[data-field]")) autosave();
});
// drag & drop between pipeline stages
let dragH = null;
let justDragged = false;

function getDropCol(target, clientX, clientY) {
  if (!target) return null;
  const col = target.closest?.(".col");
  if (col) return col;
  const board = target.closest?.(".board");
  if (board && clientX !== undefined) {
    const cols = $$(".col", board);
    for (const c of cols) {
      const rect = c.getBoundingClientRect();
      if (
        clientX >= rect.left - 12 &&
        clientX <= rect.right + 12 &&
        clientY >= rect.top - 20 &&
        clientY <= rect.bottom + 20
      ) {
        return c;
      }
    }
  }
  return null;
}

document.addEventListener("dragstart", (e) => {
  if (e.target.closest?.("button, input, select, textarea, .menu")) {
    e.preventDefault();
    return;
  }
  const c = e.target.closest?.(".card[data-h]");
  if (!c) return;
  dragH = c.dataset.h;
  c.classList.add("dragging");
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", dragH);
  }
});

document.addEventListener("dragend", (e) => {
  e.target.classList?.remove("dragging");
  $$(".card.dragging").forEach((x) => x.classList.remove("dragging"));
  $$(".col.over").forEach((c) => c.classList.remove("over"));
  dragH = null;
  justDragged = true;
  setTimeout(() => {
    justDragged = false;
  }, 150);
});

document.addEventListener("dragover", (e) => {
  if (!dragH) return;
  const c = getDropCol(e.target, e.clientX, e.clientY);
  if (c || e.target.closest?.(".board")) {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
  }
  if (c) {
    $$(".col.over").forEach((x) => x !== c && x.classList.remove("over"));
    c.classList.add("over");
  } else {
    $$(".col.over").forEach((x) => x.classList.remove("over"));
  }
});

document.addEventListener("drop", (e) => {
  if (!dragH) return;
  const c = getDropCol(e.target, e.clientX, e.clientY);
  const h = dragH || e.dataTransfer?.getData("text/plain");
  dragH = null;
  $$(".col.over").forEach((x) => x.classList.remove("over"));
  $$(".card.dragging").forEach((x) => x.classList.remove("dragging"));
  if (!c || !h) return;
  e.preventDefault();
  const st = c.dataset.stage;
  justDragged = true;
  setTimeout(() => {
    justDragged = false;
  }, 150);
  if (st && stageOf(leadOf(h)) !== st) {
    stageFor(h, st);
  }
});

/* live activity */
function addLog(x) {
  const el = document.createElement("div");
  el.className = "logline";
  el.innerHTML = `<span class="muted">${esc((x.time || "").split("T")[1] || "")}</span> <b>${esc(x.handle || "batch")}</b> <span class="muted">${esc(x.status)}</span> ${esc(x.line)}`;
  const box = $("#logs");
  box.append(el);
  while (box.children.length > 500) {
    box.firstElementChild.remove();
  }
  box.scrollTop = box.scrollHeight;
  if (x.handle === S.sel && !$("#studio").hidden) {
    const revbox = $("#revisionlogs");
    const revisionLine = el.cloneNode(true);
    revbox.append(revisionLine);
    while (revbox.children.length > 500) {
      revbox.firstElementChild.remove();
    }
    revbox.scrollTop = revbox.scrollHeight;
  }
  if (x.batch === S.st.batch) {
    if (x.status !== "log") {
      jobStatus();
    }
    if (x.handle && x.status !== "log") {
      refreshSoon();
      if (x.handle === S.sel && x.status === "done" && !$("#studio").hidden) {
        bumpNonce(x.handle);
        setTimeout(() => loadLead(S.sel, true), 500);
      }
    }
    if (x.status === "summary") {
      try {
        const a = JSON.parse(x.line);
        const summary =
          a.scraped === undefined
            ? `${a.built} built · ${a.skipped} skipped · ${a.failed} failed`
            : `${a.scraped} scraped · ${a.failed} failed`;
        toast(`Batch finished · ${summary}`);
        if ("Notification" in window && Notification.permission === "granted")
          new Notification("Studio batch complete", {
            body:
              a.scraped === undefined
                ? `${a.built} built · ${a.failed} failed`
                : `${a.scraped} scraped · ${a.failed} failed`,
          });
      } catch {}
    }
  }
}
let appInitialized = false;
function initApp() {
  if (appInitialized) return;
  appInitialized = true;

  if (!window._studioEventSource) {
    const es = new EventSource("/api/events");
    es.onmessage = (e) => {
      try {
        addLog(JSON.parse(e.data));
      } catch {}
    };
    window._studioEventSource = es;
  }

  /* boot */
  setTheme(
    localStorage.getItem("studio-theme") === "light" ? "light" : "dark",
  );
  setPalette(localStorage.getItem("studio-palette") || "studio");
  paintStudioChrome();
  S.loadingBatch = true;
  $("#batch").disabled = true;
  $("#batch").classList.add("loading-date");
  $("#batch").title = "Finding latest date from database…";
  setSyncIndicator("Finding latest date…");
  $("#jobpill").classList.add("run");
  $("#jobtext").textContent = "Finding date…";
  setView("pipeline");
  $("#btn-submit-setup")?.addEventListener("click", submitSetup);
  $("#btn-switch-local")?.addEventListener("click", enableOfflineMode);
  setInterval(() => {
    fetch("/api/heartbeat", { method: "POST" }).catch(() => {});
  }, 3000);
  window.addEventListener("beforeunload", () => {
    navigator.sendBeacon("/api/shutdown");
  });
  if ("Notification" in window && Notification.permission === "default")
    Notification.requestPermission();
  refresh(false).catch((e) => toast(e.message));
}

// Auth setup & event listeners
const authForm = $("#auth-form");
if (authForm) {
  authForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const u = $("#auth-user").value.trim();
    const p = $("#auth-pass").value;
    const errEl = $("#auth-err");
    const cardEl = $(".auth-card");

    const hash = await sha256(p);
    if (AUTH_USERS[u] && AUTH_USERS[u] === hash) {
      sessionStorage.setItem("studio_auth_user", u);
      hideAuthOverlay();
      toast(`Signed in as ${u}`);
      initApp();
    } else {
      if (errEl) {
        errEl.textContent = "Invalid username or password";
        errEl.hidden = false;
      }
      if (cardEl) {
        cardEl.classList.remove("auth-shake");
        void cardEl.offsetWidth; // force DOM reflow to restart animation
        cardEl.classList.add("auth-shake");
      }
      const passIn = $("#auth-pass");
      if (passIn) {
        passIn.value = "";
        passIn.focus();
      }
    }
  });
}

// Initial session check
if (isAuthenticated()) {
  hideAuthOverlay();
  initApp();
} else {
  showAuthOverlay();
}
