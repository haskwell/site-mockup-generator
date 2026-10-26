#!/usr/bin/env python3
"""Local dashboard for building and revising profile sites."""
from __future__ import annotations
import datetime as dt, json, os, queue, shutil, sqlite3, threading, time, uuid, webbrowser, sys
import csv, io
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field
from src.pipeline_common import MODEL, TIMEOUT_SECONDS, account_handle, find_agy, get_venv_python, run_streaming
from src.run import process_account, validate_site

REPO=Path(__file__).resolve().parents[1]; WEB=REPO/"web"
DB=Path(os.environ.get("DASHBOARD_DB",REPO/"dashboard.sqlite3"))
DEFAULTS={"websites_root":str(Path.home()/"websites"),"model":MODEL,"timeout":TIMEOUT_SECONDS,"parallelism":1,"max_posts":18,"captions":True,"headed":False,"attempts":3,"credentials":str(REPO/"config/creds.json"),"sheet_name":"websites","browser":"","sync_sheet":True}
app=FastAPI(title="Studio",docs_url=None,redoc_url=None)
events=[]; subscribers=set(); event_lock=threading.Lock(); job_lock=threading.Lock(); active_job=None
revision_queue=queue.Queue(); revision_active=False; revision_pending=0
def newest_batch():
    base=Path(DEFAULTS["websites_root"])
    dates=[]
    try:
        for entry in base.iterdir():
            if entry.is_dir():
                try:dates.append(dt.date.fromisoformat(entry.name).isoformat())
                except ValueError:pass
    except OSError:pass
    return max(dates) if dates else dt.date.today().isoformat()

selected_batch=newest_batch()

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb):
        try: return super().__exit__(exc_type,exc,tb)
        finally: self.close()

def connect():
    c=sqlite3.connect(DB,timeout=10,factory=ClosingConnection); c.row_factory=sqlite3.Row; return c

def init_db():
    DB.parent.mkdir(parents=True,exist_ok=True)
    with connect() as d:
        d.executescript("""CREATE TABLE IF NOT EXISTS leads(batch TEXT,handle TEXT,name TEXT DEFAULT '',phone TEXT DEFAULT '',area TEXT DEFAULT '',followers TEXT DEFAULT '',status TEXT DEFAULT 'queued',error TEXT DEFAULT '',site_path TEXT DEFAULT '',notes TEXT DEFAULT '',stage TEXT DEFAULT 'new',follow_up TEXT DEFAULT '',price TEXT DEFAULT '',qa TEXT DEFAULT '',created_at TEXT DEFAULT CURRENT_TIMESTAMP,updated_at TEXT DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(batch,handle));
        CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY AUTOINCREMENT,batch TEXT,handle TEXT,request TEXT,status TEXT DEFAULT 'pending',created_at TEXT DEFAULT CURRENT_TIMESTAMP,applied_at TEXT,backup_path TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT,batch TEXT,handle TEXT,status TEXT,line TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP);""")
        for k,v in DEFAULTS.items(): d.execute("INSERT OR IGNORE INTO settings VALUES(?,?)",(k,json.dumps(v)))

@app.on_event("startup")
def startup(): init_db()

def settings():
    with connect() as d: rows=d.execute("SELECT key,value FROM settings").fetchall()
    return {r["key"]:json.loads(r["value"]) for r in rows}

def clean_batch(batch):
    try:
        if dt.date.fromisoformat(batch).isoformat()!=batch:raise ValueError
    except ValueError:raise HTTPException(400,"Batch must use YYYY-MM-DD")
    return batch

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
    with connect() as d:
        d.execute("INSERT INTO logs(batch,handle,status,line) VALUES(?,?,?,?)",(item["batch"],handle,status,line))
        if handle and status in {"queued","scraping","building","scraped","done","failed"}:
            d.execute("UPDATE leads SET status=?,error=?,stage=CASE WHEN ?='done' AND stage='new' THEN 'built' ELSE stage END,updated_at=CURRENT_TIMESTAMP WHERE batch=? AND handle=?",(status,line if status=="failed" else "",status,item["batch"],handle))

class Accounts(BaseModel): text:str; batch:str|None=None
class Run(BaseModel): handles:list[str]=Field(default_factory=list); force:bool=False; rescrape:bool=False; scrape_only:bool=False
class SettingsBody(BaseModel): values:dict[str,Any]
class LeadEdit(BaseModel): name:str=""; phone:str=""; area:str=""; followers:str=""; notes:str=""; stage:str="new"; follow_up:str=""; price:str=""
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

@app.get("/",response_class=HTMLResponse)
def home(): return (WEB/"index.html").read_text()

@app.get("/api/state")
def state(batch:str|None=None):
    batch=clean_batch(batch or selected_batch); conf=settings(); base=Path(conf["websites_root"]).expanduser().resolve();root=base/batch
    batches=sorted((p.name for p in base.iterdir() if p.is_dir()),reverse=True) if base.exists() else []
    # Existing CLI-built batches predate the dashboard database. Discover them
    # on selection and seed lead rows without modifying any site files.
    if root.is_dir():
        with connect() as d:
            for account in root.iterdir():
                try:
                    handle=clean_handle(account.name)
                except HTTPException:
                    continue
                site=account/"site"/"index.html"
                if not account.is_dir() or not site.is_file():continue
                profile_path=account/f"{handle}_data"/"profile_data.json"
                summary_path=account/f"{handle}_data"/"business_data.json"
                name=phone=area=followers=""
                try:
                    profile=json.loads(profile_path.read_text());name=profile.get("name","");followers=profile.get("followers","")
                except Exception:pass
                try:
                    record=json.loads(summary_path.read_text())[0];name=record.get("name") or name;phone=record.get("phone","");area=record.get("area","")
                except Exception:pass
                d.execute("INSERT OR IGNORE INTO leads(batch,handle,name,phone,area,followers,status,site_path,qa) VALUES(?,?,?,?,? ,?,'done',?,'available')",(batch,handle,name,phone,area,followers,str(site)))
    with connect() as d:
        leads=[dict(r) for r in d.execute("SELECT * FROM leads WHERE batch=? ORDER BY updated_at DESC,handle",(batch,))]
    a=REPO/"config/accounts.txt"; auth=REPO/"config/auth.json"
    return {"batch":batch,"batches":batches,"settings":conf,"leads":leads,"accounts":a.read_text() if a.exists() else "","auth_exists":auth.exists(),"auth_mtime":dt.datetime.fromtimestamp(auth.stat().st_mtime).isoformat(timespec="minutes") if auth.exists() else ""}

@app.post("/api/accounts")
def save_accounts(b:Accounts):
    handles=parse_accounts(b.text); p=REPO/"config/accounts.txt";p.parent.mkdir(exist_ok=True);p.write_text("".join(h+"\n" for h in handles))
    b.batch=clean_batch(b.batch or selected_batch)
    with connect() as d:
        for h in handles:d.execute("INSERT OR IGNORE INTO leads(batch,handle) VALUES(?,?)",(b.batch or selected_batch,h))
    return {"handles":handles}

@app.get("/api/accounts/export")
def export_accounts():
    p=REPO/"config/accounts.txt";p.parent.mkdir(exist_ok=True);p.touch(exist_ok=True);return FileResponse(p,filename="accounts.txt")

@app.put("/api/settings")
def save_settings(b:SettingsBody):
    with connect() as d:
        for k,v in b.values.items():
            if k in DEFAULTS:d.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(k,json.dumps(v)))
    return settings()

@app.post("/api/sheets/test")
def test_sheet():
    conf=settings(); credentials=Path(conf["credentials"]).expanduser()
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
        jid=str(uuid.uuid4());active_job={"id":jid,"batch":batch,"handles":handles,"started":time.time(),"cancel":None}
    threading.Thread(target=run_worker,args=(handles,batch,force,rescrape,scrape_only,jid),daemon=True).start();return {"job_id":jid,"handles":handles}

def run_worker(handles,batch,force,rescrape,scrape_only,jid):
    global active_job
    token=threading.Event()
    with job_lock:
        if not active_job or active_job["id"]!=jid:return
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
        with connect() as d:d.execute("INSERT OR IGNORE INTO leads(batch,handle) VALUES(?,?)",(batch,current))
        emit(current,"queued","In queue",batch)
        try:
            class Log:
                def log(self,level,msg):emit(current,"log",f"{level}: {msg}",batch)
            py=os.environ.get("PIPELINE_PYTHON") or get_venv_python(REPO)
            selected_file=root/current/"selected_posts.json"
            try:selected_photos=json.loads(selected_file.read_text())
            except Exception:selected_photos=None
            rc=process_account(current,root,py,force,Log(),emit=lambda h,s,l:emit(h,s,l,batch),cancel_event=token,options={**conf,"preserve_summary":True,"rescrape":rescrape,"scrape_only":scrape_only,"selected_photos":selected_photos,"auth_path":str(REPO/"config/auth.json")})
            if rc==2:emit(current,"done","Already built; skipped",batch)
            elif rc!=0:emit(current,"failed","Build failed or cancelled",batch)
            prof=root/current/f"{current}_data"/"profile_data.json";summ=root/current/f"{current}_data"/"business_data.json"
            name=area=phone=followers=""
            try:
                p=json.loads(prof.read_text());followers=p.get("followers","");name=p.get("name","")
                r=json.loads(summ.read_text())[0];name=r.get("name") or name;area=r.get("area","");phone=r.get("phone","")
            except Exception:pass
            site_index=root/current/"site"/"index.html";site_path=str(site_index) if site_index.is_file() else ""
            qa="passed" if site_path and not validate_site(site_index.parent) else "pending"
            with connect() as d:d.execute("UPDATE leads SET name=CASE WHEN name='' THEN ? ELSE name END,phone=CASE WHEN phone='' THEN ? ELSE phone END,area=CASE WHEN area='' THEN ? ELSE area END,followers=?,site_path=?,qa=?,updated_at=CURRENT_TIMESTAMP WHERE batch=? AND handle=?",(name,phone,area,followers,site_path,qa,batch,current))
            return "scraped" if rc==0 and scrape_only else "skipped" if rc==2 else "built" if rc==0 else "failed"
        except Exception as e:emit(current,"failed",str(e),batch);return "failed"
    workers=1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(build_one,h) for h in handles]
        for future in as_completed(futures):
            key=future.result();counts[key]+=1
    emit("","summary",json.dumps(counts),batch)
    with job_lock:active_job=None

@app.post("/api/run")
def run(b:Run,batch:str|None=None):
    batch=clean_batch(batch or selected_batch)
    p=REPO/"config/accounts.txt";handles=b.handles or parse_accounts(p.read_text() if p.exists() else "")
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
    def gen():
        q=queue.Queue(maxsize=200)
        with event_lock:subscribers.add(q);history=events[-80:]
        try:
            for x in history:yield "data: "+json.dumps(x)+"\n\n"
            while True:
                try:yield "data: "+json.dumps(q.get(timeout=15))+"\n\n"
                except queue.Empty:yield ": keepalive\n\n"
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
    try:profile=json.loads((data/"profile_data.json").read_text())
    except Exception:pass
    try:summary=json.loads((data/"business_data.json").read_text())
    except Exception:pass
    for post in profile.get("posts",[]):post["preview"]=f"/media/{batch}/{handle}/{post.get('web_path','')}"
    design=account/"DESIGN.md"
    selected_file=root_for(batch)/handle/"selected_posts.json"
    try:selected=json.loads(selected_file.read_text())
    except Exception:selected=[Path(p.get("web_path","")).name for p in profile.get("posts",[])]
    return {"lead":dict(r),"profile":profile,"summary":summary,"revisions":rev,"design":design.read_text() if design.exists() else "","selected_photos":selected}

@app.post("/api/lead/{handle}/recording")
async def save_recording(handle:str,request:Request,batch:str|None=None,screen:str="desktop",extension:str="webm"):
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch)
    if screen not in {"phone","tablet","desktop"}:raise HTTPException(400,"Invalid screen size")
    if extension not in {"mp4","webm"}:raise HTTPException(400,"Invalid recording format")
    account=root_for(batch)/handle
    if not (account/"site"/"index.html").is_file():raise HTTPException(404,"Site not found")
    data=await request.body()
    if not data:raise HTTPException(400,"Recording is empty")
    recordings=account/"recordings";recordings.mkdir(parents=True,exist_ok=True)
    path=recordings/f"{handle}-{screen}.{extension}"
    path.write_bytes(data)
    return {"path":str(path)}

@app.put("/api/lead/{handle}/photos")
def save_photos(handle:str,b:PhotoSelection,batch:str|None=None):
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch);account=root_for(batch)/handle;profile_path=account/f"{handle}_data"/"profile_data.json"
    try:posts=json.loads(profile_path.read_text()).get("posts",[])
    except Exception:raise HTTPException(404,"Scraped profile not found")
    valid={Path(p.get("web_path","")).name for p in posts};files=set(b.files)
    if not files:raise HTTPException(400,"Select at least one photo")
    if not files<=valid:raise HTTPException(400,"Selection contains unknown post files")
    (account/"selected_posts.json").write_text(json.dumps(sorted(files)),encoding="utf-8")
    return {"saved":len(files)}

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
        with connect() as d:
            d.execute("DELETE FROM leads WHERE batch=? AND handle=?",(batch,handle))
            d.execute("DELETE FROM revisions WHERE batch=? AND handle=?",(batch,handle))
        removed.append(handle)
    return {"removed":removed}

@app.get("/api/leads.csv")
def export_leads(batch:str|None=None):
    batch=clean_batch(batch or selected_batch)
    with connect() as d:rows=d.execute("SELECT * FROM leads WHERE batch=? ORDER BY handle",(batch,)).fetchall()
    output=io.StringIO();writer=csv.writer(output);writer.writerow(rows[0].keys() if rows else ["handle","name","phone","area","status","stage","notes"])
    for row in rows:writer.writerow(tuple(row))
    from fastapi.responses import Response
    return Response(output.getvalue(),media_type="text/csv",headers={"Content-Disposition":f'attachment; filename="leads-{batch}.csv"'})

@app.put("/api/lead/{handle}")
def edit_lead(handle:str,b:LeadEdit,batch:str|None=None):
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch);data=root_for(batch)/handle/f"{handle}_data"/"business_data.json"
    with connect() as d:d.execute("UPDATE leads SET name=?,phone=?,area=?,followers=?,notes=?,stage=?,follow_up=?,price=?,updated_at=CURRENT_TIMESTAMP WHERE batch=? AND handle=?",(b.name,b.phone,b.area,b.followers,b.notes,b.stage,b.follow_up,b.price,batch,handle))
    data.parent.mkdir(parents=True,exist_ok=True)
    try:records=json.loads(data.read_text())
    except Exception:records=[]
    rec=records[0] if records else {};rec.update({"handle":handle,"name":b.name,"phone":b.phone,"area":b.area,"followers":b.followers})
    data.write_text(json.dumps([rec],ensure_ascii=False,indent=2)+"\n");return {"saved":True}

@app.post("/api/revision/{handle}")
def add_revision(handle:str,b:Revision,batch:str|None=None):
    if not b.request.strip():raise HTTPException(400,"Enter a revision")
    handle=clean_handle(handle);batch=clean_batch(batch or selected_batch)
    with connect() as d:rid=d.execute("INSERT INTO revisions(batch,handle,request) VALUES(?,?,?)",(batch,handle,b.request.strip())).lastrowid
    emit(handle,"revision","Revision saved",batch);return {"id":rid}

def revision_worker(handle,batch,rid,text):
    account=root_for(batch)/handle;backup_dir=account/"backups"
    try:
        before=set(backup_dir.glob("site_before_revision_*") if backup_dir.exists() else [])
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
        with connect() as d:d.execute("UPDATE revisions SET status='failed' WHERE id=?",(rid,))
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
    shutil.rmtree(site,ignore_errors=True);shutil.copytree(backup,site);emit(handle,"done","Revision undone",batch);return {"undone":True}

@app.get("/api/lead/{handle}/zip")
def zip_site(handle:str,batch:str|None=None):
    from tempfile import gettempdir
    handle=clean_handle(handle);site=root_for(clean_batch(batch or selected_batch))/handle/"site"
    if not site.is_dir():raise HTTPException(404,"Site not found")
    target=shutil.make_archive(str(Path(gettempdir())/f"studio_{handle}"),"zip",site);return FileResponse(target,filename=handle+".zip")

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

@app.get("/preview/{batch}/{handle}/{path:path}")
def preview(batch:str,handle:str,path:str="index.html"):
    handle=clean_handle(handle);batch=clean_batch(batch)
    base=(root_for(batch)/handle/"site").resolve();target=(base/path).resolve()
    if not target.is_relative_to(base) or not target.is_file():raise HTTPException(404,"Not found")
    return FileResponse(target)

@app.get("/media/{batch}/{handle}/{path:path}")
def media(batch:str,handle:str,path:str):
    handle=clean_handle(handle);batch=clean_batch(batch)
    base=(root_for(batch)/handle/f"{handle}_data").resolve();target=(base/path).resolve()
    if not target.is_relative_to(base) or not target.is_file():raise HTTPException(404,"Not found")
    return FileResponse(target)

if __name__=="__main__":
    import uvicorn
    uvicorn.run("src.app:app",host="127.0.0.1",port=int(os.environ.get("PORT",8765)))
