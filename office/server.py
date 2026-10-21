import mimetypes
import os
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from office import OfficeError, llm
from office.config import HOST, PORT, WEB
from office.jobs import Office

# Windows 레지스트리가 .js를 text/plain으로 잡으면 모듈 스크립트가 막힌다
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("font/woff2", ".woff2")

SAFE_SUFFIX = re.compile(r"\.[a-z0-9]{1,5}")
# 다른 웹사이트가 내 PC의 사무실에 명령을 보내거나(CSRF) 몰래 읽지(DNS rebinding) 못하게
LOCAL = {f"{HOST}:{PORT}", f"localhost:{PORT}"}


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def create_app(office: Office) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        office.load_history()
        office.start()
        yield

    app = FastAPI(lifespan=lifespan)

    @app.middleware("http")
    async def only_local(request, call_next):
        origin = request.headers.get("origin")
        if request.headers.get("host") not in LOCAL or (origin and origin.removeprefix("http://") not in LOCAL):
            return _error("사무실 밖에서 온 요청이라 막았어.", 403)
        return await call_next(request)

    @app.post("/api/command")
    async def command(text: str = Form(""), files: list[UploadFile] = File(default=[])):
        files = [f for f in files if f.filename]
        if not text.strip() and not files:
            return _error("명령을 입력해줘.", 400)
        job_id, job_dir = office.new_job_dir()
        saved = []
        for i, upload in enumerate(files):
            suffix = Path(upload.filename).suffix.lower()  # 원래 이름은 경로에 안 씀 (경로 탈출 방지)
            dest = job_dir / "inputs" / f"{i:02d}{suffix if SAFE_SUFFIX.fullmatch(suffix) else ''}"
            dest.write_bytes(await upload.read())
            saved.append(dest)
        office.submit(job_id, text.strip(), saved)
        return {"job_id": job_id}

    @app.get("/api/state")
    def state():
        return {**office.snapshot(), "ollama": llm.is_up(), "model": llm.model()}

    @app.post("/api/jobs/{job_id}/deploy")
    def deploy(job_id: str):
        try:
            office.submit_deploy(job_id)
        except OfficeError as e:
            return _error(str(e), 400)
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/open")
    def open_folder(job_id: str):
        if job_id not in office.jobs:
            return _error("그런 작업이 없어.", 404)
        os.startfile(office.jobs_dir / job_id)
        return {"ok": True}

    @app.post("/api/shutdown")
    def shutdown():
        threading.Timer(0.5, os._exit, [0]).start()
        return {"ok": True}

    app.mount("/files", StaticFiles(directory=office.root, check_dir=False), name="files")
    app.mount("/", StaticFiles(directory=WEB, html=True, check_dir=False), name="web")
    return app


app = create_app(Office())
