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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from office import OfficeError, llm
from office.config import HOST, MAX_UPLOAD, PORT, VERSION, WEB
from office.jobs import Office

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


def create_app(office: Office) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        office.load_history()
        office.start()
        llm.mode = office.notifier.settings.get("ai", "fast")
        threading.Thread(target=llm.warm, daemon=True, name="office-warm").start()
        threading.Thread(target=_alarms, args=(office,), daemon=True, name="office-alarms").start()
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
            names.append(Path(upload.filename.replace("\\", "/")).name[:80])
        office.submit(job_id, text.strip()[:4000], saved, ref=ref, names=names)
        return {"job_id": job_id}

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

    @app.post("/api/shutdown")
    def shutdown():
        threading.Timer(0.5, os._exit, [0]).start()
        return {"ok": True}

    app.mount("/files", StaticFiles(directory=office.root, check_dir=False), name="files")
    app.mount("/", StaticFiles(directory=WEB, html=True, check_dir=False), name="web")
    return app


app = create_app(Office())
