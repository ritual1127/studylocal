import io
import mimetypes
import os
import re
import shutil
import tempfile
import threading
import time
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from office import OfficeError, llm
from office.config import HOST, MAX_UPLOAD, PORT, VERSION, WEB
from office.jobs import Office
from office.plan import OUTPUTS
from office.remote import Remote, start_uvicorn

# Windows 레지스트리가 .js를 text/plain으로 잡으면 모듈 스크립트가 막힌다
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/woff2", ".woff2")

SAFE_SUFFIX = re.compile(r"\.[a-z0-9]{1,5}")
# 다른 웹사이트가 내 PC의 사무실에 명령을 보내거나(CSRF) 몰래 읽지(DNS rebinding) 못하게
LOCAL = {f"{HOST}:{PORT}", f"localhost:{PORT}"}
ALARM_EVERY = 15  # 초


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def tick(office: Office) -> None:
    """때가 된 일정·할 일·공부모드·아침 브리핑 알림을 보낸다."""
    for item in office.planner.due(office.notifier.settings.get("briefing", "")):
        office.notifier.send(item["title"], item["body"], item.get("reminder", False))


def _alarms(office: Office) -> None:
    while True:
        try:
            tick(office)
        except Exception:
            traceback.print_exc()
        time.sleep(ALARM_EVERY)


def _history(office: Office, limit: int = 50) -> list[dict]:
    with office.lock:
        rows = [{"job": job.id, "title": job.title or job.text[:30], **a}
                for job in office.jobs.values() for a in job.approvals]
    return sorted(rows, key=lambda r: r["time"], reverse=True)[:limit]


async def _take_command(office: Office, text: str, ref: str, files: list[UploadFile]):
    files = [f for f in files if f.filename]
    if not text.strip() and not files:
        return _error("명령을 입력해줘.", 400)
    if ref and office.material_of(ref) is None:
        return _error("고른 자료를 못 찾았어. 보관함에서 다시 골라줘.", 400)
    job_id, job_dir = office.new_job_dir()
    saved, names = [], []
    for i, upload in enumerate(files):
        data = await upload.read()
        if len(data) > MAX_UPLOAD:
            shutil.rmtree(job_dir, ignore_errors=True)
            return _error(f"'{Path(upload.filename).name}' 파일이 너무 커. {MAX_UPLOAD // 1_000_000}MB까지만 돼.", 400)
        suffix = Path(upload.filename).suffix.lower()  # 원래 이름은 경로에 안 씀 (경로 탈출 방지)
        dest = job_dir / "inputs" / f"{i:02d}{suffix if SAFE_SUFFIX.fullmatch(suffix) else ''}"
        dest.write_bytes(data)
        saved.append(dest)
        names.append(Path(upload.filename.replace('\\', "/")).name[:80])
    office.submit(job_id, text.strip()[:4000], saved, ref=ref, names=names)
    return {"job_id": job_id}


def create_app(office: Office, remote: Remote | None = None) -> FastAPI:
    if remote is None:
        remote = Remote(office.root / "remote.json",
                        start_server=lambda host: start_uvicorn(lambda: create_remote_app(office, remote), host),
                        notify=lambda title, body: office.notifier.send(title, body))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        office.load_history()
        office.start()
        llm.mode = office.notifier.settings.get("ai", "fast")
        threading.Thread(target=llm.warm, daemon=True, name="office-warm").start()
        threading.Thread(target=_alarms, args=(office,), daemon=True, name="office-alarms").start()
        threading.Thread(target=remote.apply, daemon=True, name="office-remote-start").start()  # 켜 둔 폰 연결 되살리기
        yield

    app = FastAPI(lifespan=lifespan)

    @app.middleware("http")
    async def only_local(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.headers.get("host") not in LOCAL or (origin and origin.removeprefix("http://") not in LOCAL):
            return _error("사무실 밖에서 온 요청이라 막았어.", 403)
        return await call_next(request)

    @app.exception_handler(OfficeError)
    async def office_error(request: Request, exc: OfficeError):
        return _error(str(exc), 400)

    # ---- 업무 지시 ----
    @app.post("/api/command")
    async def command(text: str = Form(""), ref: str = Form(""), files: list[UploadFile] = File(default=[])):
        return await _take_command(office, text, ref, files)

    @app.get("/api/state")
    def state():
        return {**office.snapshot(), "planner": office.planner.view(), "ollama": llm.is_up(), "model": llm.model(),
                "ai": llm.mode, "version": VERSION}

    # ---- 작업 카드 버튼 ----
    @app.post("/api/jobs/{job_id}/deploy")
    def deploy(job_id: str):
        office.submit_deploy(job_id)
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/approve")
    def approve(job_id: str, body: dict = Body(default={})):
        office.approve(job_id, str(body.get("comment") or ""))
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/reject")
    def reject(job_id: str, body: dict = Body(default={})):
        office.reject(job_id, str(body.get("comment") or ""))
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/retry")
    def retry(job_id: str):
        office.retry(job_id)
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/delete")
    def delete(job_id: str):
        office.delete(job_id)
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/open")
    def open_folder(job_id: str):
        if job_id not in office.jobs:
            return _error("그런 작업이 없어.", 404)
        os.startfile(office.jobs_dir / job_id)
        return {"ok": True}

    # ---- 대표실 ----
    @app.get("/api/ceo")
    def ceo():
        return {"stats": office.stats(), "auto": dict(office.auto), "history": _history(office)}

    @app.post("/api/auto")
    def auto(body: dict = Body(...)):
        return office.set_auto(body)

    # ---- 플래너 ----
    planner = office.planner

    @app.post("/api/todos")
    def add_todo(body: dict = Body(...)):
        return planner.add_todo(body.get("text"), body.get("date", ""), body.get("time", ""))

    @app.post("/api/todos/{todo_id}")
    def update_todo(todo_id: str, body: dict = Body(...)):
        return planner.update_todo(todo_id, body)

    @app.post("/api/todos/{todo_id}/delete")
    def delete_todo(todo_id: str):
        planner.delete_todo(todo_id)
        return {"ok": True}

    @app.post("/api/events")
    def add_event(body: dict = Body(...)):
        return planner.add_event(body.get("title"), body.get("date"), body.get("time", ""), body.get("kind", "일정"),
                                 body.get("remind"), body.get("repeat", "none"))

    @app.post("/api/events/{event_id}/delete")
    def delete_event(event_id: str):
        planner.delete_event(event_id)
        return {"ok": True}

    @app.post("/api/focus")
    def focus(body: dict = Body(...)):
        return planner.start_focus(body.get("minutes"), body.get("task", ""), body.get("kind", "focus"))

    @app.post("/api/focus/stop")
    def focus_stop():
        return {"minutes": planner.stop_focus()}

    # ---- 설정 ----
    def settings_view():
        return {"settings": dict(office.notifier.settings), "history": list(office.notifier.history)}

    @app.get("/api/settings")
    def get_settings():
        return settings_view()

    @app.post("/api/settings")
    def set_settings(body: dict = Body(...)):
        new = office.notifier.update(body)
        if new["ai"] != llm.mode:
            llm.mode = new["ai"]
            threading.Thread(target=llm.warm, daemon=True, name="office-warm").start()
        return settings_view()

    @app.post("/api/settings/test")
    def test_alert():
        return {"errors": office.notifier.send("테스트 알림", "ritual의 공부 사무실 알림이 잘 와!")}

    @app.get("/api/backup")
    def backup():
        fd, tmp = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        archive = shutil.make_archive(tmp[:-4], "zip", root_dir=office.root)
        return FileResponse(archive, media_type="application/zip",
                            filename=f"ritual-office-backup-{time.strftime('%Y%m%d-%H%M')}.zip",
                            background=BackgroundTask(os.unlink, archive))

    # ---- 폰 연결 ----
    @app.get("/api/remote")
    def remote_status():
        return remote.status()

    @app.post("/api/remote")
    def remote_update(body: dict = Body(...)):
        return remote.update(body)

    @app.get("/api/remote/qr")
    def remote_qr():
        link = remote.status()["link"]
        if not link:
            return _error("폰 연결을 먼저 켜줘.", 404)
        import qrcode
        import qrcode.image.svg

        buf = io.BytesIO()
        qrcode.make(link, image_factory=qrcode.image.svg.SvgPathImage, box_size=12, border=2).save(buf)
        return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})

    @app.post("/api/shutdown")
    def shutdown():
        threading.Timer(0.5, os._exit, [0]).start()
        return {"ok": True}

    app.mount("/files", StaticFiles(directory=office.root, check_dir=False), name="files")
    app.mount("/", StaticFiles(directory=WEB, html=True, check_dir=False), name="web")
    return app


# ---- 폰 서버 (8766): 토큰 쿠키가 있어야 들어온다. PC 전용 기능(종료·백업·설정·폴더 열기)은 없다 ----
COOKIE = "ritual_k"
LOCKED = """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>공부 사무실</title><body style="background:#14111f;color:#f3eefe;font-family:sans-serif;padding:24px;line-height:1.6">
<h1 style="font-size:20px">잠겨 있어</h1><p>PC의 공부 사무실 설정 탭에 있는 QR이나 링크로 다시 들어와줘.</p></body></html>"""
PHONE_JOB = ("id", "no", "text", "title", "status", "reply", "error", "created", "seconds", "names", "revision", "answer",
             "warnings")


def _phone_state(office: Office) -> dict:
    snap = office.snapshot()
    jobs = []
    for j in snap["jobs"]:
        item = {k: j.get(k) for k in PHONE_JOB}
        item["results"] = {k: v for k, v in j["results"].items()
                           if isinstance(v, str) and (v.startswith("/files/jobs/") or k == "deploy_url")}
        item["outputs"] = [s for s in j["steps"] if s in OUTPUTS]
        item["last"] = j["approvals"][-1] if j["approvals"] else None
        jobs.append(item)
    view = office.planner.view()
    return {"jobs": jobs, "working": [s["name"] for s in snap["staff"].values() if s["state"] == "working"],
            "pending": sum(j["status"] == "review" for j in jobs),
            "planner": {k: view[k] for k in ("today", "weekday", "todos", "today_events", "dday", "focus", "stats")}}


def create_remote_app(office: Office, remote: Remote) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def need_token(request: Request, call_next):
        key = request.query_params.get("k")
        if key is not None:  # 처음엔 링크·QR의 ?k=토큰 → 쿠키로 바꾸고 주소창에서 지운다
            if not remote.check(key):
                return HTMLResponse(LOCKED, status_code=401)
            response = RedirectResponse(request.url.path, status_code=302)
            response.set_cookie(COOKIE, key, max_age=90 * 86400, httponly=True, samesite="strict",
                                secure=request.headers.get("x-forwarded-proto") == "https")
            return response
        if not remote.check(request.cookies.get(COOKIE)):
            return HTMLResponse(LOCKED, status_code=401)
        if request.method != "GET" and request.headers.get("x-ritual") != "1":  # 다른 사이트가 몰래 보내는 요청(CSRF) 차단
            return _error("폰 화면에서만 보낼 수 있어.", 403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(OfficeError)
    async def office_error(request: Request, exc: OfficeError):
        return _error(str(exc), 400)

    @app.get("/")
    def home():
        return RedirectResponse("/m")

    @app.get("/m")
    def phone_page():
        return FileResponse(WEB / "m.html")

    for name in ("m.js", "m.css", "ui.js", "logo-pixel.png", "icon.ico"):
        app.add_api_route(f"/{name}", lambda name=name: FileResponse(WEB / name), methods=["GET"])

    @app.get("/api/m/state")
    def phone_state():
        return {**_phone_state(office), "ollama": llm.is_up()}

    @app.post("/api/m/command")
    async def phone_command(text: str = Form(""), ref: str = Form(""), files: list[UploadFile] = File(default=[])):
        return await _take_command(office, text, ref, files)

    @app.post("/api/m/jobs/{job_id}/approve")
    def phone_approve(job_id: str, body: dict = Body(default={})):
        office.approve(job_id, str(body.get("comment") or ""))
        return {"ok": True}

    @app.post("/api/m/jobs/{job_id}/reject")
    def phone_reject(job_id: str, body: dict = Body(default={})):
        office.reject(job_id, str(body.get("comment") or ""))
        return {"ok": True}

    @app.post("/api/m/todos/{todo_id}")
    def phone_todo(todo_id: str, body: dict = Body(...)):
        return office.planner.update_todo(todo_id, {"done": body.get("done")})

    app.mount("/fonts", StaticFiles(directory=WEB / "fonts", check_dir=False), name="fonts")
    app.mount("/files/jobs", StaticFiles(directory=office.jobs_dir, check_dir=False), name="jobs")
    return app


app = create_app(Office())
