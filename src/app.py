#!/usr/bin/env python3
"""Local dashboard for building and revising profile sites."""
from __future__ import annotations
import datetime as dt, json, os, queue, shutil, sqlite3, threading, time, uuid, webbrowser, sys, asyncio
import csv, io
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field
from src.pipeline_common import MODEL, TIMEOUT_SECONDS, account_handle, find_agy, get_venv_python, run_streaming
from src.run import process_account, validate_site
from src.d1_client import (
    get_current_user,
    get_db_connection,
    is_d1_configured,
    is_d1_offline,
    is_local_mode,
    set_d1_offline,
    set_local_mode,
    sync_local_to_d1,
)
from src.r2_storage import (
    delete_lead_assets,
    delete_site_assets,
    delete_recording,
    download_lead_folder,
    download_recording,
    download_site,
    get_lead_json,
    get_lead_text,
    get_presigned_recording_url,
    get_preview_url,
    get_r2_mtime,
    get_r2_object,
    get_recording_url,
    get_s3_client,
    has_r2_site,
    is_r2_configured,
    list_recordings,
    upload_file,
    upload_recording,
    upload_site,
)
from tempfile import gettempdir

REPO=Path(__file__).resolve().parents[1]; WEB=REPO/"web"
DB=Path(os.environ.get("DASHBOARD_DB",REPO/"dashboard.sqlite3"))
DEFAULTS={"websites_root":"websites","model":MODEL,"timeout":TIMEOUT_SECONDS,"parallelism":1,"max_posts":18,"captions":True,"headed":False,"attempts":3,"credentials":"config/creds.json","sheet_name":"websites","browser":"","sync_sheet":True,"local_mode":False}

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app=FastAPI(title="Studio",docs_url=None,redoc_url=None,lifespan=lifespan)

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    host = (request.headers.get("host") or "").split(":")[0].strip().lower()
    if host not in {"127.0.0.1", "localhost", "testserver", "::1"}:
        return Response("Invalid Host header", status_code=403)
    if request.method in {"POST", "PUT", "DELETE", "PATCH"}:
        if request.headers.get("X-Studio") != "1":
            return Response("Missing or invalid X-Studio header", status_code=403)
        ct = request.headers.get("Content-Type", "").strip().lower()
        if not ct.startswith("application/json"):
            return Response("Content-Type must be application/json", status_code=415)
    return await call_next(request)
events=[]; subscribers=set(); event_lock=threading.Lock(); job_lock=threading.Lock(); active_job=None
revision_queue=queue.Queue(); revision_active=False; revision_pending=0

def connect():
    return get_db_connection(DB)

def newest_batch():
    dates=[]
    try:
        with connect() as d:
            rows=d.execute("SELECT DISTINCT batch FROM leads").fetchall()
            for r in rows:
                b=r["batch"]
                try:dates.append(dt.date.fromisoformat(b).isoformat())
                except (ValueError, TypeError):pass
    except Exception as exc:
        import logging
        logging.getLogger("uvicorn.error").debug("Could not query batches from db: %s", exc)
    if not dates:
        base=Path(DEFAULTS["websites_root"])
        try:
            for entry in base.iterdir():
                if entry.is_dir():
                    try:dates.append(dt.date.fromisoformat(entry.name).isoformat())
                    except ValueError:pass
        except OSError:pass
    return max(dates) if dates else dt.date.today().isoformat()

_cached_selected_batch: str | None = None

def get_selected_batch() -> str:
    global _cached_selected_batch
    if _cached_selected_batch is None:
        _cached_selected_batch = newest_batch()
    return _cached_selected_batch

class _LazySelectedBatch:
    def __str__(self) -> str:
        return get_selected_batch()
    def __repr__(self) -> str:
        return repr(get_selected_batch())
    def __bool__(self) -> bool:
        return bool(get_selected_batch())
    def __eq__(self, other: Any) -> bool:
        return str(self) == other
    def __hash__(self) -> int:
        return hash(str(self))

selected_batch = _LazySelectedBatch()

def init_db():
    try:
        with connect() as d:
            if not isinstance(d, sqlite3.Connection) and not is_local_mode():
                # When cloud D1 is active, absolutely no queries run at startup: tables already exist.
                return
            DB.parent.mkdir(parents=True, exist_ok=True)
            d.executescript("""CREATE TABLE IF NOT EXISTS leads(batch TEXT,handle TEXT,name TEXT DEFAULT '',phone TEXT DEFAULT '',area TEXT DEFAULT '',followers TEXT DEFAULT '',status TEXT DEFAULT 'queued',error TEXT DEFAULT '',site_path TEXT DEFAULT '',notes TEXT DEFAULT '',stage TEXT DEFAULT 'new',follow_up TEXT DEFAULT '',price TEXT DEFAULT '',qa TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,locked_by TEXT DEFAULT '',locked_at TEXT DEFAULT '',has_recording INTEGER DEFAULT 0,PRIMARY KEY(batch,handle));
            CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY AUTOINCREMENT,batch TEXT,handle TEXT,request TEXT,status TEXT DEFAULT 'pending',created_at TEXT DEFAULT CURRENT_TIMESTAMP,applied_at TEXT,backup_path TEXT DEFAULT '');
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
            CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT,batch TEXT,handle TEXT,status TEXT,line TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);""")
            try:d.execute("ALTER TABLE leads ADD COLUMN locked_by TEXT DEFAULT ''")
            except Exception:pass
            try:d.execute("ALTER TABLE leads ADD COLUMN locked_at TEXT DEFAULT ''")
            except Exception:pass
            try:d.execute("ALTER TABLE leads ADD COLUMN has_recording INTEGER DEFAULT 0")
            except Exception:pass
            try:d.execute("UPDATE leads SET site_path = '/preview/' || batch || '/' || handle || '/index.html' WHERE site_path LIKE 'http%'")
            except Exception:pass
            for k,v in DEFAULTS.items():
                d.execute("INSERT OR IGNORE INTO settings VALUES(?,?)",(k,json.dumps(v)))
    except Exception:
        pass

def resolve_credentials_path(path_str: str | None = None) -> Path:
    env_creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if env_creds and Path(env_creds).is_file():
        return Path(env_creds).resolve()
    local_creds = (REPO / "config" / "creds.json").resolve()
    if local_creds.is_file():
        return local_creds
    if path_str:
        p = Path(path_str).expanduser()
        if not p.is_absolute():
            p = (REPO / p).resolve()
        if p.is_file():
            return p.resolve()
    return local_creds

def resolve_websites_root(root_str: str | None = None) -> Path:
    env_root = os.environ.get("WEBSITES_ROOT")
    if env_root:
        p = Path(env_root).expanduser().resolve()
    elif root_str:
        p = Path(root_str).expanduser()
        if not p.is_absolute():
            p = (Path.home() / p).resolve()
        elif p.is_dir():
            p = p.resolve()
    else:
        p = (Path.home() / "websites").resolve()
    if not p.exists():
        import logging
        logging.getLogger("uvicorn.error").warning("Configured websites root directory does not exist: %s", p)
    return p

_settings_cache: dict[str, Any] | None = None

def settings():
    global _settings_cache
    if _settings_cache is not None:
        return dict(_settings_cache)
    try:
        with connect() as d: rows=d.execute("SELECT key,value FROM settings").fetchall()
        conf = {r["key"]:json.loads(r["value"]) for r in rows if not str(r["key"]).startswith("_")}
    except Exception:
        conf = dict(DEFAULTS)
    for k, v in DEFAULTS.items():
        if k not in conf: conf[k] = v
    for num_key in ("timeout", "parallelism", "max_posts", "attempts"):
        val = conf.get(num_key)
        if isinstance(val, bool) or not isinstance(val, (int, float)) or int(val) < 1:
            conf[num_key] = DEFAULTS[num_key]
        else:
            conf[num_key] = int(val)
    conf["local_mode"] = bool(conf.get("local_mode", False) or is_local_mode())
    conf["credentials"] = str(resolve_credentials_path(conf.get("credentials")))
    conf["websites_root"] = str(resolve_websites_root(conf.get("websites_root")))
    _settings_cache = dict(conf)
    return conf

def clean_batch(batch):
    batch_str = str(batch)
    try:
        if dt.date.fromisoformat(batch_str).isoformat() != batch_str:
            raise ValueError
    except ValueError:
        raise HTTPException(400, "Batch must use YYYY-MM-DD")
    return batch_str

def clean_handle(handle):
    try:valid=account_handle(handle)
    except ValueError as exc:raise HTTPException(400,str(exc))
    if valid!=handle:raise HTTPException(400,"Use the normalized Instagram handle")
    return handle

def root_for(batch): return Path(settings()["websites_root"]).expanduser().resolve()/clean_batch(batch)

def emit(handle,status,line="",batch=None):
    item={"id":str(uuid.uuid4()),"handle":handle,"status":status,"line":line,"batch":batch or selected_batch,"time":dt.datetime.now().isoformat(timespec="seconds")}
    with event_lock:
        events.append(item)
        if len(events)>1200: del events[:300]
        for q in tuple(subscribers):
            try:q.put_nowait(item)
            except queue.Full:pass
    try:
        with connect() as d:
            if status != "log":
                d.execute("INSERT INTO logs(batch,handle,status,line) VALUES(?,?,?,?)",(item["batch"],handle,status,line))
            if handle and status in {"queued","scraping","building","scraped","done","failed"}:
                d.execute("UPDATE leads SET status=?,error=?,stage=CASE WHEN ?='done' AND stage='new' THEN 'built' ELSE stage END,updated_at=CURRENT_TIMESTAMP WHERE batch=? AND handle=?",(status,line if status=="failed" else "",status,item["batch"],handle))
    except Exception:
        pass

class Accounts(BaseModel): text:str; batch:str|None=None
class Run(BaseModel): handles:list[str]=Field(default_factory=list); force:bool=False; rescrape:bool=False; scrape_only:bool=False
class SettingsBody(BaseModel): values:dict[str,Any]
class LeadEdit(BaseModel): name:str=""; phone:str=""; area:str=""; followers:str=""; notes:str=""; stage:str="new"; follow_up:str=""; price:str=""
class LeadStageUpdate(BaseModel): stage:str="new"
class Revision(BaseModel): request:str
class PhotoSelection(BaseModel): files:list[str]
class BulkInput(BaseModel): handles:list[str]; mode:str="site"

def parse_accounts(text):
    out=[]; seen=set()
    for line in text.splitlines():
        raw=line.split("#",1)[0].strip()
        if not raw:continue
        try:h=account_handle(raw)
        except ValueError as e:raise HTTPException(400,str(e))
        if h.casefold() not in seen:out.append(h);seen.add(h.casefold())
    return out

@app.get("/api/ping")
def ping():
    return {"status": "ok"}

@app.post("/api/sync/d1")
def sync_d1():
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    database_id = (
        os.environ.get("D1_DATABASE_ID", "").strip()
        or os.environ.get("CLOUDFLARE_D1_DATABASE_ID", "").strip()
    )
    if not (account_id and api_token and database_id):
        raise HTTPException(400, "Cloudflare D1 credentials are not configured in .env")
    from src.d1_client import D1Connection
    d1 = D1Connection(account_id, database_id, api_token)
    try:
        synced = sync_local_to_d1(DB, d1, DEFAULTS)
    except Exception as exc:
        raise HTTPException(500, f"Sync to D1 failed: {exc}")
    finally:
        try:
            d1.close()
        except Exception:
            pass
    return {"synced": synced}

@app.get("/",response_class=HTMLResponse)
def home(): return (WEB/"index.html").read_text(encoding="utf-8")

@app.get("/styles.css")
def styles(): return FileResponse(WEB/"styles.css", media_type="text/css")

@app.get("/script.js")
def script(): return FileResponse(WEB/"script.js", media_type="application/javascript")

@app.get("/assets/studio.png")
def studio_logo(): return FileResponse(REPO/"assets"/"studio.png")

@app.get("/api/state")
def state(batch:str|None=None):
    conf=settings(); base=Path(conf["websites_root"]).expanduser().resolve()
    db_batches=set()
    try:
        with connect() as d:
            for r in d.execute("SELECT DISTINCT batch FROM leads").fetchall():
                db_batches.add(r["batch"])
    except Exception:pass
    disk_batches=set(p.name for p in base.iterdir() if p.is_dir()) if base.exists() else set()
    batches=sorted(db_batches | disk_batches,reverse=True)
    if not batch:
        dates=[]
        for b in batches:
            try:
                dt.date.fromisoformat(str(b))
                dates.append(str(b))
            except (ValueError, TypeError):pass
        batch = dates[0] if dates else dt.date.today().isoformat()
    batch = clean_batch(batch)
    global _cached_selected_batch
    _cached_selected_batch = batch
    if batch not in batches:batches.insert(0,batch)
    root=base/batch
    # Existing CLI-built batches predate the dashboard database. Discover them
    # on selection and seed lead rows without modifying any site files.
    if root.is_dir():
        with connect() as d:
            existing_handles = {r["handle"] for r in d.execute("SELECT handle FROM leads WHERE batch=?", (batch,)).fetchall()}
            to_insert = []
            for account in root.iterdir():
                try:
                    handle=clean_handle(account.name)
                except HTTPException:
                    continue
                if handle in existing_handles:
                    continue
                site=account/"site"/"index.html"
                if not account.is_dir() or not site.is_file():continue
                profile_path=account/f"{handle}_data"/"profile_data.json"
                summary_path=account/f"{handle}_data"/"business_data.json"
                name=phone=area=followers=""
                try:
                    profile=json.loads(profile_path.read_text(encoding="utf-8"));name=profile.get("name","");followers=profile.get("followers","")
                except Exception:pass
                try:
                    record=json.loads(summary_path.read_text(encoding="utf-8"))[0];name=record.get("name") or name;phone=record.get("phone","");area=record.get("area","")
                except Exception:pass
                to_insert.append((batch,handle,name,phone,area,followers,'done',str(site),'available'))
                existing_handles.add(handle)
            if to_insert:
                d.executemany("INSERT OR IGNORE INTO leads(batch,handle,name,phone,area,followers,status,site_path,qa) VALUES(?,?,?,?,?,?,?,?,?)", to_insert)
    with connect() as d:
        leads=[dict(r) for r in d.execute("SELECT * FROM leads WHERE batch=? ORDER BY updated_at DESC,handle",(batch,))]
    for l in leads:
        has_rec = bool(l.get("has_recording"))
        if not has_rec:
            h = l.get("handle") or ""
            rec_dir = root / h / "recordings"
            if rec_dir.is_dir():
                try:
                    has_rec = any(f.suffix.lower() in {".webm", ".mp4"} for f in rec_dir.iterdir() if f.is_file())
                except OSError:
                    pass
        l["has_recording"] = 1 if has_rec else 0
    a=REPO/"config/accounts.txt"; auth=REPO/"config/auth.json"
    return {"batch":batch,"batches":batches,"settings":conf,"leads":leads,"accounts":a.read_text(encoding="utf-8") if a.exists() else "","auth_exists":auth.exists(),"auth_mtime":dt.datetime.fromtimestamp(auth.stat().st_mtime).isoformat(timespec="minutes") if auth.exists() else "","local_mode":is_local_mode(),"d1_offline":is_local_mode()}

@app.post("/api/accounts")
def save_accounts(b:Accounts):
    handles=parse_accounts(b.text); p=REPO/"config/accounts.txt";p.parent.mkdir(exist_ok=True);p.write_text("".join(h+"\n" for h in handles),encoding="utf-8")
    b.batch=clean_batch(b.batch or selected_batch)
    with connect() as d:
        for h in handles:d.execute("INSERT OR IGNORE INTO leads(batch,handle) VALUES(?,?)",(b.batch or selected_batch,h))
    return {"handles":handles}

@app.get("/api/accounts/export")
def export_accounts():
    p=REPO/"config/accounts.txt";p.parent.mkdir(exist_ok=True);p.touch(exist_ok=True);return FileResponse(p,filename="accounts.txt")

@app.put("/api/settings")
def save_settings(b:SettingsBody):
    cleaned: dict[str, Any] = {}
    for k, v in b.values.items():
        if k not in DEFAULTS:
            continue
        if k in {"timeout", "parallelism", "max_posts", "attempts"}:
            if v is None or v == "" or isinstance(v, bool):
                raise HTTPException(400, f"{k} must be a positive integer")
            try:
                iv = int(v)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{k} must be a positive integer")
            if iv < 1:
                raise HTTPException(400, f"{k} must be at least 1")
            cleaned[k] = iv
        elif k == "local_mode":
            cleaned[k] = bool(v)
            set_local_mode(bool(v))
        else:
            cleaned[k] = v
    with connect() as d:
        for k, v in cleaned.items():
            d.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,json.dumps(v)))
        if is_local_mode() and cleaned:
            try:
                row = d.execute("SELECT value FROM settings WHERE key='_dirty_settings'").fetchone()
                dirty = set(json.loads(row["value"])) if row else set()
                dirty.update(cleaned.keys())
                d.execute("INSERT INTO settings VALUES('_dirty_settings',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(sorted(dirty)),))
            except Exception:
                pass
    global _settings_cache
    _settings_cache = None
    return settings()

@app.post("/api/sheets/test")
def test_sheet():
    conf=settings(); credentials=resolve_credentials_path(conf.get("credentials"))
    if not credentials.is_file():
        raise HTTPException(400,f"Google Sheets credentials file not found at: {credentials}")
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        auth=Credentials.from_service_account_file(str(credentials),scopes=["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive.readonly"])
        client=gspread.authorize(auth);client.open(conf["sheet_name"])
        return {"ok":True,"message":"Connected to "+conf["sheet_name"]}
    except Exception as exc: raise HTTPException(400,str(exc))

@app.get("/api/health")
def health_check():
    import importlib.util
    agy_path = find_agy()
    checks={"agy":bool(agy_path),"playwright":importlib.util.find_spec("playwright") is not None,"browser":False}
    if checks["playwright"]:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True);browser.close()
            checks["browser"]=True
        except Exception:pass
    return {"checks":checks,"paths":{"agy":agy_path},"ok":all(checks.values())}

def queue_run(handles,batch,force,rescrape,scrape_only=False):
    global active_job
    with job_lock:
        if active_job or revision_active or not revision_queue.empty():raise HTTPException(409,"A batch or revision is already running or queued")
        jid=str(uuid.uuid4());token=threading.Event();active_job={"id":jid,"batch":batch,"handles":handles,"started":time.time(),"cancel":token}
    threading.Thread(target=run_worker,args=(handles,batch,force,rescrape,scrape_only,jid,token),daemon=True).start();return {"job_id":jid,"handles":handles}

def run_worker(handles,batch,force,rescrape,scrape_only,jid,token=None):
    global active_job
    with job_lock:
        if not active_job or active_job["id"]!=jid:return
        if token is None:
            token=active_job.get("cancel") or threading.Event()
            active_job["cancel"]=token
    conf=settings();root=root_for(batch);counts={"scraped":0,"failed":0} if scrape_only else {"built":0,"skipped":0,"failed":0}
    try:root.mkdir(parents=True,exist_ok=True)
    except Exception as exc:
        for h in handles:emit(h,"failed",str(exc),batch)
        failure_counts={"scraped":0,"failed":len(handles)} if scrape_only else {"built":0,"skipped":0,"failed":len(handles)}
        emit("","summary",json.dumps(failure_counts),batch)
        with job_lock:active_job=None
        return
    def build_one(current):
        try:
            user=get_current_user()
            with connect() as d:
                d.execute("INSERT OR IGNORE INTO leads(batch,handle) VALUES(?,?)",(batch,current))
                cur=d.execute("UPDATE leads SET locked_by=?,locked_at=CURRENT_TIMESTAMP WHERE batch=? AND handle=? AND (locked_by='' OR locked_by IS NULL OR locked_by=? OR locked_at < datetime('now','-15 minutes'))",(user,batch,current,user))
                if cur.rowcount == 0:
                    r=d.execute("SELECT locked_by FROM leads WHERE batch=? AND handle=?",(batch,current)).fetchone()
                    locked_by=dict(r).get("locked_by","another user") if r else "another user"
                    emit(current,"failed",f"Account currently locked by {locked_by}",batch)
                    return "failed"
            emit(current,"queued","In queue",batch)
            class Log:
                def log(self,level,msg):emit(current,"log",f"{level}: {msg}",batch)
            py=os.environ.get("PIPELINE_PYTHON") or get_venv_python(REPO)
            selected_file=root/current/"selected_posts.json"
            try:selected_photos=json.loads(selected_file.read_text(encoding="utf-8"))
            except Exception:
                selected_photos=get_lead_json(batch,current,"selected_posts.json") if is_r2_configured() else None
            rc=process_account(current,root,py,force,Log(),emit=lambda h,s,l:emit(h,s,l,batch),cancel_event=token,options={**conf,"preserve_summary":True,"rescrape":rescrape,"scrape_only":scrape_only,"selected_photos":selected_photos,"auth_path":str(REPO/"config/auth.json")})
            if rc==2:emit(current,"done","Already built; skipped",batch)
            elif rc!=0:emit(current,"failed","Build failed or cancelled",batch)
            prof=root/current/f"{current}_data"/"profile_data.json";summ=root/current/f"{current}_data"/"business_data.json"
            name=area=phone=followers=""
            try:
                p=json.loads(prof.read_text(encoding="utf-8"));followers=p.get("followers","");name=p.get("name","")
                rec=json.loads(summ.read_text(encoding="utf-8"))[0];name=rec.get("name") or name;area=rec.get("area","");phone=rec.get("phone","")
            except Exception:pass
            site_index=root/current/"site"/"index.html"
            is_valid_local=site_index.is_file() and not validate_site(site_index.parent)
            has_remote=has_r2_site(batch,current) if is_r2_configured() else False
            preview_url=get_preview_url(batch,current,"index.html") if (is_valid_local and is_r2_configured()) or has_remote else None
            site_path=preview_url or (str(site_index) if site_index.is_file() else "")
            qa="passed" if (is_valid_local or has_remote) else "pending"
            with connect() as d:d.execute("UPDATE leads SET name=CASE WHEN name='' THEN ? ELSE name END,phone=CASE WHEN phone='' THEN ? ELSE phone END,area=CASE WHEN area='' THEN ? ELSE area END,followers=?,site_path=?,qa=?,locked_by='',locked_at='',updated_at=CURRENT_TIMESTAMP WHERE batch=? AND handle=?",(name,phone,area,followers,site_path,qa,batch,current))
            return "scraped" if rc==0 and scrape_only else "skipped" if rc==2 else "built" if rc==0 else "failed"
        except Exception as e:
            try:
                with connect() as d:d.execute("UPDATE leads SET locked_by='',locked_at='' WHERE batch=? AND handle=?",(batch,current))
            except Exception:pass
            emit(current,"failed",str(e),batch);return "failed"
    workers=max(1,int(conf.get("parallelism",1)))
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures=[pool.submit(build_one,h) for h in handles]
            for future in as_completed(futures):
                try:
                    key=future.result();counts[key]+=1
                except Exception:
                    counts["failed"]+=1
    finally:
        emit("","summary",json.dumps(counts),batch)
        with job_lock:active_job=None

@app.post("/api/run")
def run(b:Run,batch:str|None=None):
    batch=clean_batch(batch or selected_batch)
    p=REPO/"config/accounts.txt"
    raw_handles=b.handles or parse_accounts(p.read_text(encoding="utf-8") if p.exists() else "")
    handles=[clean_handle(h) for h in raw_handles]
    return queue_run(handles,batch,b.force,b.rescrape,b.scrape_only)

@app.post("/api/cancel")
def cancel():
    with job_lock:
        if not active_job:raise HTTPException(409,"No active queue")
        if active_job.get("cancel"):active_job["cancel"].set()
    return {"cancelled":True}

@app.get("/api/job")
def job():
    with job_lock:return {"active":bool(active_job or revision_active),"batch_active":bool(active_job),"id":active_job.get("id") if active_job else None,"handles":active_job.get("handles",[]) if active_job else [],"revision_active":revision_active,"revision_pending":revision_pending}

@app.get("/api/events")
def stream(request:Request):
    with event_lock:
        if len(subscribers) >= 50:
            raise HTTPException(503, "Too many active subscribers")
        q=queue.Queue(maxsize=200)
        subscribers.add(q);history=list(events[-80:])
    async def gen():
        try:
            for x in history:yield "data: "+json.dumps(x)+"\n\n"
            while True:
                if hasattr(request, "is_disconnected") and callable(request.is_disconnected):
                    try:
                        res = request.is_disconnected()
                        if asyncio.iscoroutine(res):
                            if await res:
                                break
                        elif isinstance(res, bool) and res:
                            break
                    except Exception:
                        pass
                try:
                    item = q.get_nowait()
                    yield "data: "+json.dumps(item)+"\n\n"
                except queue.Empty:
                    try:
                        item = await asyncio.to_thread(q.get, True, 0.5)
                        yield "data: "+json.dumps(item)+"\n\n"
                    except queue.Empty:
                        yield ": keepalive\n\n"
        finally:
            with event_lock:subscribers.discard(q)
    return StreamingResponse(gen(),media_type="text/event-stream",headers={"Cache-Control":"no-cache"})

@app.get("/api/lead/{handle}")
def lead(handle:str,batch:str|None=None):
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch)
    with connect() as d:
        r=d.execute("SELECT * FROM leads WHERE batch=? AND handle=?",(batch,handle)).fetchone()
        rev=[dict(x) for x in d.execute("SELECT * FROM revisions WHERE batch=? AND handle=? ORDER BY id DESC",(batch,handle))]
    if not r:raise HTTPException(404,"Lead not found")
    account=root_for(batch)/handle;data=account/f"{handle}_data";profile={};summary=[]
    try:profile=json.loads((data/"profile_data.json").read_text(encoding="utf-8"))
    except Exception:pass
    try:summary=json.loads((data/"business_data.json").read_text(encoding="utf-8"))
    except Exception:pass
    design_candidates=[account/"site"/"DESIGN.md",account/"DESIGN.md",account/"site"/"design.md",account/"design.md"]
    design_content=None
    for cand in design_candidates:
        if cand.is_file():
            try:
                design_content=cand.read_text(encoding="utf-8")
                break
            except Exception:pass
    local_cand = next((c for c in design_candidates if c.is_file()), None)
    local_dmtime = local_cand.stat().st_mtime if local_cand else None

    selected_file=root_for(batch)/handle/"selected_posts.json"
    selected=None
    try:selected=json.loads(selected_file.read_text(encoding="utf-8"))
    except Exception:pass
    recordings={}
    local_recs=account/"recordings"
    if local_recs.is_dir():
        for f in local_recs.iterdir():
            if f.is_file() and f.suffix.lower() in {".webm",".mp4"}:
                for s in ["desktop","tablet","phone"]:
                    if f"-{s}." in f.name:recordings[s]=f.name
    r2_mtime=None
    if is_r2_configured():
        def resolve_design():
            if local_dmtime is not None:
                r2_dmtime = get_r2_mtime(f"{batch}/{handle}/site/DESIGN.md") or get_r2_mtime(f"{batch}/{handle}/DESIGN.md")
                if not r2_dmtime or r2_dmtime <= local_dmtime:
                    return design_content
            return get_lead_text(batch, handle, "DESIGN.md") or design_content

        r2_tasks={}
        with ThreadPoolExecutor(max_workers=6) as pool:
            if not profile:r2_tasks["profile"]=pool.submit(get_lead_json,batch,handle,"profile_data.json")
            if not summary:r2_tasks["summary"]=pool.submit(get_lead_json,batch,handle,"business_data.json")
            r2_tasks["design"]=pool.submit(resolve_design)
            if selected is None:r2_tasks["selected"]=pool.submit(get_lead_json,batch,handle,"selected_posts.json")
            r2_tasks["recordings"]=pool.submit(list_recordings,batch,handle)
            r2_tasks["site_mtime"]=pool.submit(get_r2_mtime,f"{batch}/{handle}/site/index.html")
            if "profile" in r2_tasks:
                try:profile=r2_tasks["profile"].result() or {}
                except Exception:profile={}
            if "summary" in r2_tasks:
                try:summary=r2_tasks["summary"].result() or []
                except Exception:summary=[]
            if "design" in r2_tasks:
                try:design_content=r2_tasks["design"].result() or ""
                except Exception:design_content=design_content or ""
            if "selected" in r2_tasks:
                try:selected=r2_tasks["selected"].result()
                except Exception:selected=None
            if "recordings" in r2_tasks:
                try:r2_recs=r2_tasks["recordings"].result() or []
                except Exception:r2_recs=[]
                for r2_rec in r2_recs:
                    for s in ["desktop","tablet","phone"]:
                        if f"-{s}." in r2_rec:recordings[s]=r2_rec
            if "site_mtime" in r2_tasks:
                try:r2_mtime=r2_tasks["site_mtime"].result()
                except Exception:r2_mtime=None
    if design_content is None:design_content=""
    for post in profile.get("posts",[]):post["preview"]=f"/media/{batch}/{handle}/{post.get('web_path','')}"
    if selected is None:selected=[Path(p.get("web_path","")).name for p in profile.get("posts",[])]
    lead_dict=dict(r)
    cloud_newer=False
    if is_r2_configured():
        sp=lead_dict.get("site_path") or ""
        if not sp or (sp.startswith("/") and not Path(sp).exists()):
            if r2_mtime is not None:
                lead_dict["site_path"]=f"/preview/{batch}/{handle}/index.html"
            else:
                r2_url=get_preview_url(batch,handle,"index.html",verify_exists=False)
                if r2_url and has_r2_site(batch,handle):
                    lead_dict["site_path"]=r2_url
        site_index=root_for(batch)/handle/"site"/"index.html"
        if r2_mtime and site_index.is_file() and r2_mtime > site_index.stat().st_mtime:
            cloud_newer=True
    return {"lead":lead_dict,"profile":profile,"summary":summary,"revisions":rev,"design":design_content,"selected_photos":selected,"recordings":recordings,"cloud_newer":cloud_newer}

@app.post("/api/lead/{handle}/recording")
async def save_recording(handle:str,request:Request,batch:str|None=None,screen:str="desktop",extension:str="webm"):
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch)
    if screen not in {"phone","tablet","desktop"}:raise HTTPException(400,"Invalid screen size")
    if extension not in {"mp4","webm"}:raise HTTPException(400,"Invalid recording format")
    account=root_for(batch)/handle
    site_file=account/"site"/"index.html"
    has_site=site_file.is_file()
    if not has_site:
        with connect() as d:
            row=d.execute("SELECT site_path, status FROM leads WHERE batch=? AND handle=?",(batch,handle)).fetchone()
            row_dict=dict(row) if row else {}
            if row_dict and (row_dict.get("site_path") or row_dict.get("status") in {"done","built"}):
                has_site=True
        if not has_site and is_r2_configured():
            has_site=has_r2_site(batch,handle)
    if not has_site:raise HTTPException(404,"Site not found")
    data=await request.body()
    if not data:raise HTTPException(400,"Recording is empty")
    recordings=account/"recordings";recordings.mkdir(parents=True,exist_ok=True)
    filename=f"{handle}-{screen}.{extension}"
    path=recordings/filename
    path.write_bytes(data)
    with connect() as d:
        d.execute("UPDATE leads SET has_recording=1, updated_at=CURRENT_TIMESTAMP WHERE batch=? AND handle=?",(batch,handle))
    r2_url=None
    if is_r2_configured():
        r2_url=upload_recording(path,batch,handle,filename)
    return {"path":str(path),"filename":filename,"r2_url":r2_url,"screen":screen}

@app.get("/api/lead/{handle}/recording/{screen}")
def get_recording(handle:str,screen:str,batch:str|None=None,download:bool=False):
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch)
    if screen not in {"phone","tablet","desktop"}:raise HTTPException(400,"Invalid screen size")
    account=root_for(batch)/handle
    recordings_dir=account/"recordings"
    local_file=None; filename=None
    for ext in ["webm","mp4"]:
        f=recordings_dir/f"{handle}-{screen}.{ext}"
        if f.is_file():
            local_file=f; filename=f.name; break
    if is_r2_configured():
        r2_filename=None
        for rec in list_recordings(batch,handle):
            if rec.startswith(f"{handle}-{screen}."):
                r2_filename=rec; break
        if r2_filename:
            presigned_url=get_presigned_recording_url(batch,handle,r2_filename,download=download)
            if presigned_url:
                from fastapi.responses import RedirectResponse
                return RedirectResponse(presigned_url,status_code=302)
            elif download and not local_file:
                temp_file=Path(gettempdir())/f"rec_{handle}_{screen}_{r2_filename}"
                if download_recording(batch,handle,r2_filename,temp_file):
                    return FileResponse(temp_file,filename=r2_filename,media_type="video/webm" if r2_filename.endswith(".webm") else "video/mp4")
    if local_file and local_file.is_file():
        headers={"Content-Disposition":f'attachment; filename="{filename}"'} if download else {}
        return FileResponse(local_file,headers=headers,media_type="video/webm" if filename.endswith(".webm") else "video/mp4")
    raise HTTPException(404,"Recording not found")

@app.delete("/api/lead/{handle}/recording/{screen}")
def delete_lead_recording_screen(handle:str,screen:str,batch:str|None=None):
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch)
    if screen not in {"phone","tablet","desktop"}:raise HTTPException(400,"Invalid screen size")
    account=root_for(batch)/handle
    recordings_dir=account/"recordings"
    deleted_local=0
    if recordings_dir.is_dir():
        for f in list(recordings_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in {".webm",".mp4"}:
                if f"-{screen}." in f.name or f.name.startswith(f"{handle}-{screen}.") or f.name.startswith(f"{screen}."):
                    try:
                        f.unlink()
                        deleted_local+=1
                    except OSError:pass
        try:
            if not any(recordings_dir.iterdir()):
                recordings_dir.rmdir()
        except OSError:pass

    deleted_r2=0
    if is_r2_configured():
        try:
            deleted_r2=delete_recording(batch,handle,screen=screen)
        except Exception as exc:
            raise HTTPException(502,f"Failed to delete recording from R2: {exc}")

    remaining={}
    if recordings_dir.is_dir():
        for f in recordings_dir.iterdir():
            if f.is_file() and f.suffix.lower() in {".webm",".mp4"}:
                for s in ["desktop","tablet","phone"]:
                    if f"-{s}." in f.name:remaining[s]=f.name
    if is_r2_configured():
        for r2_rec in list_recordings(batch,handle):
            for s in ["desktop","tablet","phone"]:
                if f"-{s}." in r2_rec:remaining[s]=r2_rec

    has_rec = 1 if len(remaining) > 0 else 0
    new_stage = None
    with connect() as d:
        row = d.execute("SELECT stage, site_path FROM leads WHERE batch=? AND handle=?",(batch,handle)).fetchone()
        row_dict = dict(row) if row else {}
        current_stage = row_dict.get("stage")
        new_stage = current_stage
        if not has_rec and current_stage == "recorded":
            has_site = (account/"site"/"index.html").is_file() or bool(row_dict.get("site_path"))
            new_stage = "built" if has_site else "new"
        d.execute("UPDATE leads SET has_recording=?, stage=?, updated_at=CURRENT_TIMESTAMP WHERE batch=? AND handle=?",(has_rec,new_stage,batch,handle))

    return {
        "deleted": True,
        "deleted_local": deleted_local,
        "deleted_r2": deleted_r2,
        "screen": screen,
        "has_recording": has_rec,
        "remaining": remaining,
        "stage": new_stage
    }

@app.delete("/api/lead/{handle}/recording")
def delete_lead_recording_all(handle:str,batch:str|None=None):
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch)
    account=root_for(batch)/handle
    recordings_dir=account/"recordings"
    deleted_local=0
    if recordings_dir.is_dir():
        for f in list(recordings_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in {".webm",".mp4"}:
                try:
                    f.unlink()
                    deleted_local+=1
                except OSError:pass
        try:
            if not any(recordings_dir.iterdir()):
                recordings_dir.rmdir()
        except OSError:pass

    deleted_r2=0
    if is_r2_configured():
        try:
            deleted_r2=delete_recording(batch,handle,screen=None)
        except Exception as exc:
            raise HTTPException(502,f"Failed to delete recordings from R2: {exc}")

    new_stage = None
    with connect() as d:
        row = d.execute("SELECT stage, site_path FROM leads WHERE batch=? AND handle=?",(batch,handle)).fetchone()
        row_dict = dict(row) if row else {}
        current_stage = row_dict.get("stage")
        new_stage = current_stage
        if current_stage == "recorded":
            has_site = (account/"site"/"index.html").is_file() or bool(row_dict.get("site_path"))
            new_stage = "built" if has_site else "new"
        d.execute("UPDATE leads SET has_recording=0, stage=?, updated_at=CURRENT_TIMESTAMP WHERE batch=? AND handle=?",(new_stage,batch,handle))

    return {
        "deleted": True,
        "deleted_local": deleted_local,
        "deleted_r2": deleted_r2,
        "screen": "all",
        "has_recording": 0,
        "remaining": {},
        "stage": new_stage
    }

@app.put("/api/lead/{handle}/photos")
def save_photos(handle:str,b:PhotoSelection,batch:str|None=None):
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch);account=root_for(batch)/handle;profile_path=account/f"{handle}_data"/"profile_data.json"
    posts=[]
    try:posts=json.loads(profile_path.read_text(encoding="utf-8")).get("posts",[])
    except Exception:
        if is_r2_configured():
            prof=get_lead_json(batch,handle,"profile_data.json")
            if prof and isinstance(prof,dict):
                posts=prof.get("posts",[])
    if not posts:raise HTTPException(404,"Scraped profile not found")
    valid={Path(p.get("web_path","")).name for p in posts};files=set(b.files)
    if not files:raise HTTPException(400,"Select at least one photo")
    if not files<=valid:raise HTTPException(400,"Selection contains unknown post files")
    account.mkdir(parents=True,exist_ok=True)
    target_file=account/"selected_posts.json"
    target_file.write_text(json.dumps(sorted(files)),encoding="utf-8")
    if is_r2_configured():
        upload_file(target_file,f"{batch}/{handle}/selected_posts.json","application/json")
    return {"saved":len(files)}

@app.post("/api/lead/{handle}/unlock")
def unlock_lead(handle:str,batch:str|None=None):
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch)
    with connect() as d:
        d.execute("UPDATE leads SET locked_by='',locked_at='' WHERE batch=? AND handle=?",(batch,handle))
    return {"unlocked":True}

@app.post("/api/lead/delete")
def delete_leads(b:BulkInput,batch:str|None=None):
    if b.mode not in {"site","folder"}:raise HTTPException(400,"mode must be 'site' or 'folder'")
    batch=clean_batch(batch or selected_batch);root=root_for(batch);removed=[]
    with job_lock:
        if active_job and any(handle in active_job.get("handles",[]) for handle in b.handles):
            raise HTTPException(409,"Cannot delete a lead while it is in the build queue")
    for raw in b.handles:
        handle=clean_handle(raw);account=(root/handle).resolve()
        if not account.is_relative_to(root.resolve()):raise HTTPException(400,"Unsafe account path")
        site=(account/"site").resolve()
        if b.mode=="folder":
            if account.exists():shutil.rmtree(account)
        elif site.is_relative_to(account) and site.exists():shutil.rmtree(site)
        if b.mode == "folder":
            delete_lead_assets(batch,handle)
        else:
            delete_site_assets(batch,handle)
        with connect() as d:
            d.execute("DELETE FROM leads WHERE batch=? AND handle=?",(batch,handle))
            d.execute("DELETE FROM revisions WHERE batch=? AND handle=?",(batch,handle))
            if is_d1_offline():
                try:
                    row = d.execute("SELECT value FROM settings WHERE key='_deleted_leads'").fetchone()
                    deleted_list = json.loads(row["value"]) if row else []
                    if [batch, handle] not in deleted_list:
                        deleted_list.append([batch, handle])
                    d.execute("INSERT INTO settings VALUES('_deleted_leads',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(deleted_list),))
                except Exception:
                    pass
        removed.append(handle)
    return {"removed":removed}

@app.get("/api/leads.csv")
def export_leads(batch:str|None=None):
    batch=clean_batch(batch or selected_batch)
    with connect() as d:rows=d.execute("SELECT * FROM leads WHERE batch=? ORDER BY handle",(batch,)).fetchall()
    output=io.StringIO();writer=csv.writer(output)
    keys=list(rows[0].keys()) if rows else ["handle","name","phone","area","status","stage","notes"]
    writer.writerow(keys)
    for row in rows:
        vals=[]
        for k in keys:
            v=row[k]
            if isinstance(v,str) and v.startswith(("=","+","-","@")):
                v="'"+v
            vals.append(v)
        writer.writerow(vals)
    return Response(output.getvalue(),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="leads-{batch}.csv"'})

@app.put("/api/lead/{handle}")
def edit_lead(handle:str,b:LeadEdit,batch:str|None=None):
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch);data=root_for(batch)/handle/f"{handle}_data"/"business_data.json"
    with connect() as d:d.execute("UPDATE leads SET name=?,phone=?,area=?,followers=?,notes=?,stage=?,follow_up=?,price=?,updated_at=CURRENT_TIMESTAMP WHERE batch=? AND handle=?",(b.name,b.phone,b.area,b.followers,b.notes,b.stage,b.follow_up,b.price,batch,handle))
    data.parent.mkdir(parents=True,exist_ok=True)
    try:records=json.loads(data.read_text(encoding="utf-8"))
    except Exception:
        records=get_lead_json(batch,handle,"business_data.json") if is_r2_configured() else []
        if not isinstance(records,list):records=[]
    rec=records[0] if records else {};rec.update({"handle":handle,"name":b.name,"phone":b.phone,"area":b.area,"followers":b.followers})
    data.write_text(json.dumps([rec],ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    if is_r2_configured():
        upload_file(data,f"{batch}/{handle}/media/business_data.json","application/json")
    return {"saved":True}

@app.patch("/api/lead/{handle}/stage")
@app.patch("/api/lead/{handle}")
def update_lead_stage(handle:str,b:LeadStageUpdate,batch:str|None=None):
    st = b.stage.strip().lower()
    allowed = {"new", "built", "recorded", "sent", "replied", "won", "lost"}
    if st not in allowed:
        raise HTTPException(400, f"Invalid stage: {st}. Must be one of {sorted(allowed)}")
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch)
    with connect() as d:
        d.execute("UPDATE leads SET stage=?,updated_at=CURRENT_TIMESTAMP WHERE batch=? AND handle=?",(st,batch,handle))
    return {"saved":True,"handle":handle,"stage":st}

@app.post("/api/lead/{handle}/archive")
def archive_lead(handle:str,batch:str|None=None):
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch)
    deleted=delete_lead_assets(batch,handle)
    with connect() as d:
        d.execute("UPDATE leads SET stage='lost',updated_at=CURRENT_TIMESTAMP WHERE batch=? AND handle=?",(batch,handle))
    return {"archived":True,"deleted_assets":deleted}

@app.post("/api/revision/{handle}")
def add_revision(handle:str,b:Revision,batch:str|None=None):
    if not b.request.strip():raise HTTPException(400,"Enter a revision")
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch)
    with connect() as d:rid=d.execute("INSERT INTO revisions(batch,handle,request) VALUES(?,?,?)",(batch,handle,b.request.strip())).lastrowid
    emit(handle,"revision","Revision saved",batch);return {"id":rid}

def revision_worker(handle,batch,rid,text):
    account=root_for(batch)/handle;backup_dir=account/"backups"
    before=set(backup_dir.glob("site_before_revision_*") if backup_dir.exists() else [])
    try:
        class Log:
            def log(self,level,msg):emit(handle,"log",f"{level}: {msg}",batch)
        from src.revisions import revise
        conf=settings()
        rc=revise(handle,text,root_for(batch),{handle},Log(),emit=lambda h,s,l:emit(h,s,l,batch),model=conf["model"],timeout=int(conf["timeout"]))
        created=list(set(backup_dir.glob("site_before_revision_*"))-before) if backup_dir.exists() else []
        backup=max(created,key=lambda p:p.stat().st_mtime) if created else None
        status="applied" if rc==0 else "failed"
        with connect() as d:d.execute("UPDATE revisions SET status=?,applied_at=CASE WHEN ?='applied' THEN CURRENT_TIMESTAMP ELSE applied_at END,backup_path=? WHERE id=?",(status,status,str(backup or ""),rid))
    except Exception as e:
        created=list(set(backup_dir.glob("site_before_revision_*"))-before) if backup_dir.exists() else []
        backup=max(created,key=lambda p:p.stat().st_mtime) if created else None
        if backup and backup.is_dir() and not (account/"site"/"index.html").is_file():
            shutil.rmtree(account/"site",ignore_errors=True)
            shutil.copytree(backup,account/"site")
        with connect() as d:d.execute("UPDATE revisions SET status='failed',backup_path=CASE WHEN ? != '' THEN ? ELSE backup_path END WHERE id=?",(str(backup or ""),str(backup or ""),rid))
        emit(handle,"failed",str(e),batch)
    finally:
        global revision_active,revision_pending
        try: revision_queue.task_done()
        except ValueError: pass
        with job_lock:
            revision_pending=max(0,revision_pending-1)
            revision_active=revision_pending>0

def revision_queue_worker():
    global revision_active
    while True:
        handle,batch,rid,text=revision_queue.get()
        revision_worker(handle,batch,rid,text)

threading.Thread(target=revision_queue_worker,daemon=True).start()

@app.post("/api/revision/{handle}/{rid}/apply")
def apply_revision(handle:str,rid:int,batch:str|None=None):
    global revision_active,revision_pending
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch)
    with job_lock:
        if active_job:raise HTTPException(409,"Revisions are disabled while a batch is running")
    with connect() as d:r=d.execute("SELECT request FROM revisions WHERE id=? AND batch=? AND handle=?",(rid,batch,handle)).fetchone()
    if not r:raise HTTPException(404,"Revision not found")
    with job_lock:
        if active_job:raise HTTPException(409,"Revisions are disabled while a batch is running")
        revision_active=True
        revision_pending+=1
        revision_queue.put((handle,batch,rid,r["request"]))
        position=revision_pending
    emit(handle,"revision_queued",f"Revision queued · position {position}",batch)
    return {"started":True,"queued":position>1,"position":position}

@app.post("/api/revision/{handle}/{rid}/undo")
def undo_revision(handle:str,rid:int,batch:str|None=None):
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch)
    with connect() as d:r=d.execute("SELECT backup_path FROM revisions WHERE id=? AND batch=?",(rid,batch)).fetchone()
    if not r or not r["backup_path"]:raise HTTPException(404,"No backup")
    base=root_for(batch)/handle;backup=Path(r["backup_path"]).resolve();site=base/"site"
    if not backup.is_relative_to((base/"backups").resolve()) or not backup.is_dir():raise HTTPException(400,"Invalid backup")
    shutil.rmtree(site,ignore_errors=True);shutil.copytree(backup,site)
    now=time.time()
    for item in site.rglob("*"):
        if item.is_file():
            os.utime(item,(now,now))
    if is_r2_configured():
        try:
            s3=get_s3_client()
            bucket=os.environ["R2_BUCKET_NAME"].strip()
            prefix=f"{batch}/{handle}/site/"
            paginator=s3.get_paginator("list_objects_v2")
            pages=paginator.paginate(Bucket=bucket,Prefix=prefix)
            to_delete=[]
            for page in pages:
                for obj in page.get("Contents",[]):
                    rel=obj["Key"][len(prefix):]
                    if rel and not (site/rel).is_file():
                        to_delete.append({"Key":obj["Key"]})
            if to_delete:
                s3.delete_objects(Bucket=bucket,Delete={"Objects":to_delete})
        except Exception:pass
        upload_site(site,batch,handle)
        touch_time=time.time()+2
        for item in site.rglob("*"):
            if item.is_file():
                os.utime(item,(touch_time,touch_time))
    emit(handle,"done","Revision undone",batch);return {"undone":True}

@app.get("/api/lead/{handle}/zip")
def zip_site(handle:str,batch:str|None=None,mode:str="site"):
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch)
    if mode not in {"site","full"}:raise HTTPException(400,"mode must be 'site' or 'full'")
    account=root_for(batch)/handle
    target_name=f"{handle}-site" if mode=="site" else f"{handle}-full"
    archive_base=str(Path(gettempdir())/f"studio_{handle}_{mode}_{uuid.uuid4().hex}")
    cleanup_dir=None
    target=None
    if mode=="site":
        site=account/"site"
        site_index=site/"index.html"
        local_ok=site.is_dir() and site_index.is_file()
        r2_newer=False
        if is_r2_configured() and local_ok:
            r2_mtime=get_r2_mtime(f"{batch}/{handle}/site/index.html")
            if r2_mtime is not None and r2_mtime > site_index.stat().st_mtime:
                r2_newer=True
        if local_ok and not r2_newer:
            target=shutil.make_archive(archive_base,"zip",site)
        elif is_r2_configured():
            temp_site=Path(gettempdir())/f"r2_site_{batch}_{handle}_{uuid.uuid4().hex}"
            temp_site.mkdir(parents=True,exist_ok=True)
            if download_site(batch,handle,temp_site):
                target=shutil.make_archive(archive_base,"zip",temp_site)
            shutil.rmtree(temp_site,ignore_errors=True)
        if not target:raise HTTPException(404,"Website files not found")
    else:
        site_index=account/"site"/"index.html"
        local_ok=account.is_dir()
        r2_newer=False
        if is_r2_configured() and local_ok:
            r2_mtime=get_r2_mtime(f"{batch}/{handle}/site/index.html")
            if r2_mtime is not None and (not site_index.is_file() or r2_mtime > site_index.stat().st_mtime):
                r2_newer=True
        if local_ok and not r2_newer:
            target=shutil.make_archive(archive_base,"zip",account)
        elif is_r2_configured():
            temp_lead=Path(gettempdir())/f"r2_lead_{batch}_{handle}_{uuid.uuid4().hex}"
            temp_lead.mkdir(parents=True,exist_ok=True)
            if download_lead_folder(batch,handle,temp_lead):
                target=shutil.make_archive(archive_base,"zip",temp_lead)
            shutil.rmtree(temp_lead,ignore_errors=True)
        if not target:raise HTTPException(404,"Account files not found")

    def _cleanup():
        Path(target).unlink(missing_ok=True)

    return FileResponse(target,filename=f"{target_name}.zip",media_type="application/zip",background=BackgroundTask(_cleanup))

@app.get("/api/open/{handle}")
def open_profile(handle:str):
    url=f"https://www.instagram.com/{account_handle(handle)}/";threading.Thread(target=webbrowser.open,args=(url,),daemon=True).start();return {"url":url}

@app.post("/api/auth/clear")
def clear_auth():
    p=REPO/"config/auth.json"
    if p.exists():p.unlink()
    return {"cleared":True}

@app.post("/api/auth/login")
def login():
    def work():
        from playwright.sync_api import sync_playwright
        pth=REPO/"config/auth.json";pth.parent.mkdir(parents=True,exist_ok=True)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=False);ctx=browser.new_context(locale="en-US");page=ctx.new_page();page.goto("https://www.instagram.com/accounts/login/")
            try:page.wait_for_function("!location.pathname.includes('/accounts/login')",timeout=600000);ctx.storage_state(path=str(pth));emit("","done","Instagram session saved")
            except Exception as e:emit("","failed",str(e))
            browser.close()
    threading.Thread(target=work,daemon=True).start();return {"started":True}

SCROLL_SHIM = """<script>
window.addEventListener('message', function(e) {
  if (e.data && e.data.action === 'autoScroll') {
    var max = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    if (!max) { window.parent.postMessage({ action: 'scrollDone' }, '*'); return; }
    var dur = Math.min(60000, Math.max(6000, max / 0.11));
    var t0 = performance.now() + 1200;
    var ease = function(t) { return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; };
    function step(now) {
      var k = Math.min(1, Math.max(0, (now - t0) / dur));
      window.scrollTo(0, max * ease(k));
      if (k < 1) requestAnimationFrame(step);
      else setTimeout(function() { window.parent.postMessage({ action: 'scrollDone' }, '*'); }, 1500);
    }
    requestAnimationFrame(step);
  }
});
</script>"""

@app.api_route("/preview/{batch}/{handle}/{path:path}", methods=["GET", "HEAD"])
def preview(batch:str,handle:str,path:str="index.html"):
    handle=clean_handle(handle);batch=clean_batch(batch)
    clean_path=Path(path).as_posix().lstrip("/")
    if ".." in Path(clean_path).parts or clean_path.startswith("/"):
        raise HTTPException(400,"Invalid path")
    base=(root_for(batch)/handle/"site").resolve()
    target=(base/clean_path).resolve()
    local_exists=target.is_file() and target.is_relative_to(base)
    headers={"Content-Security-Policy":"sandbox allow-scripts allow-forms;","Cache-Control":"private, no-cache"}

    if is_r2_configured():
        r2_key=f"{batch}/{handle}/site/{clean_path}"
        r2_mtime=get_r2_mtime(r2_key)
        if r2_mtime is not None:
            if not local_exists or r2_mtime > target.stat().st_mtime:
                obj=get_r2_object(r2_key)
                if obj:
                    body,ct=obj
                    try:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(body)
                        os.utime(target, (r2_mtime, r2_mtime))
                    except Exception:pass
                    if clean_path.endswith(".html"):
                        html_text = body.decode("utf-8", errors="replace")
                        if "</body>" in html_text:
                            html_text = html_text.replace("</body>", SCROLL_SHIM + "</body>")
                            return Response(content=html_text, media_type=ct, headers=headers)
                        elif "</html>" in html_text:
                            html_text = html_text.replace("</html>", SCROLL_SHIM + "</html>")
                            return Response(content=html_text, media_type=ct, headers=headers)
                    return Response(content=body,media_type=ct,headers=headers)

    if local_exists:
        if clean_path.endswith(".html"):
            try:
                html_text = target.read_text(encoding="utf-8", errors="replace")
                if "</body>" in html_text:
                    html_text = html_text.replace("</body>", SCROLL_SHIM + "</body>")
                    return Response(content=html_text, media_type="text/html; charset=utf-8", headers=headers)
                elif "</html>" in html_text:
                    html_text = html_text.replace("</html>", SCROLL_SHIM + "</html>")
                    return Response(content=html_text, media_type="text/html; charset=utf-8", headers=headers)
            except Exception:pass
        return FileResponse(target,headers=headers)
    raise HTTPException(404,"Not found")

@app.get("/media/{batch}/{handle}/{path:path}")
def media(batch:str,handle:str,path:str):
    handle=clean_handle(handle);batch=clean_batch(batch)
    clean_path=Path(path).as_posix().lstrip("/")
    if ".." in Path(clean_path).parts or clean_path.startswith("/"):
        raise HTTPException(400,"Invalid path")
    base=(root_for(batch)/handle/f"{handle}_data").resolve()
    target=(base/clean_path).resolve()
    local_exists=target.is_file() and target.is_relative_to(base)
    headers={"Cache-Control":"private, no-cache"}
    if is_r2_configured():
        r2_key=f"{batch}/{handle}/media/{clean_path}"
        if local_exists:
            r2_mtime=get_r2_mtime(r2_key)
            if r2_mtime is not None and r2_mtime > target.stat().st_mtime:
                obj=get_r2_object(r2_key)
                if obj:
                    body,ct=obj
                    try:
                        target.parent.mkdir(parents=True,exist_ok=True)
                        target.write_bytes(body)
                        os.utime(target,(r2_mtime,r2_mtime))
                    except Exception:pass
                    return Response(content=body,media_type=ct,headers=headers)
        else:
            obj=get_r2_object(r2_key)
            if obj:
                body,ct=obj
                return Response(content=body,media_type=ct,headers=headers)
    if local_exists:
        return FileResponse(target,headers=headers)
    raise HTTPException(404,"Not found")

if __name__=="__main__":
    import uvicorn
    reload_opt = os.environ.get("STUDIO_RELOAD", "").strip().lower() in {"1", "true", "yes"}
    uvicorn.run("src.app:app",host="127.0.0.1",port=int(os.environ.get("PORT",8765)),reload=reload_opt)
