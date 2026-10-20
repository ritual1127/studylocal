# ritual의 공부 사무실 1단계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 바탕화면 아이콘으로 실행되는 픽셀 아트 사무실 앱에서, 로컬 qwen3.5 직원들이 프린트 → PDF 노트, 자료 → 문제 웹(Vercel 배포), 문학 작품 가져오기를 처리한다.

**Architecture:** FastAPI 로컬 서버(127.0.0.1:8765)의 웹 화면을 Edge 앱 창으로 띄운다. 명령은 작업 대기열 하나(워커 스레드 하나)에서 순서대로 처리한다: 실장(LLM 라우터, JSON) → 단계 함수(scan / literature / pdf / quiz). LLM 호출은 전부 Ollama `/api/chat` 한 곳을 거치고, PDF는 Edge headless 인쇄, 배포는 Vercel CLI가 맡는다.

**Tech Stack:** Python 3.14 (uv), FastAPI + uvicorn + python-multipart, Pillow, pypdfium2, Ollama 0.40 (`qwen3.5:latest`), Edge headless, Vercel CLI, 바닐라 HTML/CSS/JS, Galmuri11 2.40.3, pytest + httpx.

**Spec:** `docs/superpowers/specs/2026-10-21-ritual-study-office-design.md`

## Global Constraints

- 프로젝트 루트 `C:\Users\smile\OneDrive\Desktop\프로젝트\63_로컬 ai 사무실` 은 한글·공백이 들어간 경로다. 경로는 항상 `Path`와 리스트 인자로 다루고, 셸 문자열로 이어붙이지 않는다.
- 모든 `uv` 명령은 같은 줄 앞에 `$env:UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\ritual-office\venv";` 를 붙인다 (가상환경을 OneDrive 밖에 둔다. 도구 호출마다 환경변수가 초기화되므로 매번 붙인다).
- 런타임 의존성은 `fastapi`, `uvicorn`, `python-multipart`, `pillow`, `pypdfium2` 다섯 개, dev는 `pytest`, `httpx`. 그 밖은 추가 금지: HTTP는 `urllib.request`, HTML 파싱은 `html.parser`, 템플릿은 `office.fill()`의 `__KEY__` 치환.
- LLM 호출은 전부 `office.llm.chat` / `office.llm.chat_json` 을 거친다. 기본 모델 `qwen3.5:latest`, `think: false`, `num_ctx` 16384, `keep_alive` `"10m"`, `stream: false`.
- 서버는 `127.0.0.1:8765` 에만 바인딩한다.
- 사용자에게 보이는 메시지는 한국어 반말이고 `OfficeError(메시지)`로 전달한다. 화면에 스택트레이스를 보이지 않는다 (예상 못 한 예외는 로그 파일로).
- 결과물은 `output/` (git 제외), 앱 데이터(venv, Edge 프로필, 로그)는 `%LOCALAPPDATA%\ritual-office`.
- 공개 배포(`vercel deploy`)는 사용자가 화면에서 [배포]를 두 번 눌렀을 때만 실행한다. 배포를 누른 문제만 사이트 폴더에 들어간다.
- 디자인: `PALETTE = ["#9337FD", "#E036F0", "#FC34CA", "#FD389C", "#FD633E", "#FC7135"]`, 바탕 `#14111f`, 픽셀 폰트 Galmuri11 2.40.3, `border-radius` 금지, 이미지·캔버스는 `image-rendering: pixelated`, 애니메이션은 `steps()`.
- `.ps1` 파일은 UTF-8 **BOM 포함**으로 저장한다 (Windows PowerShell 5.1은 BOM이 없으면 CP949로 읽어 한글이 깨진다).
- Task마다 끝에 커밋한다. conventional 메시지(feat/fix/test/chore), 본문 마지막 줄 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. `git add`는 파일을 지정해서 한다.

## Review Focus

1. 휴대폰 사진에 회전 정보(EXIF)가 있어 옆으로 누운 채 OCR되면 결과가 엉망이 된다 → 읽기 전에 세운다. (Task 3 `test_exif_rotated_photo_is_upright`)
2. 한글·공백 경로에서 PDF가 안 만들어지거나 한글이 □로 나온다 → 한글 폴더에서도 PDF가 생기고 Galmuri·맑은 고딕이 박힌다. (Task 5 `test_pdf_has_korean_fonts`)
3. AI가 깨진 JSON이나 쓸모없는 문제를 돌려준다 → 1회 재시도 후 한국어 에러, 다음 작업은 정상 처리. (Task 1 `test_chat_json_*`, Task 6 `test_make_quiz_retries_once_then_caps_count`, Task 8 `test_step_error_marks_job_and_worker_survives`)
4. Ollama가 꺼져 있거나 모델이 없다 → "Ollama 켜줘" / "`ollama pull`" 안내. (Task 1 `test_chat_down_raises_korean_hint`, `test_missing_model_hint`)
5. 자료에 `<script>`, `</script>` 같은 글자가 섞여 있다 → PDF·문제 웹이 깨지거나 스크립트가 실행되지 않는다. (Task 5 `test_note_html_escapes_and_contains_content`, Task 6 `test_quiz_html_survives_script_injection`)

---

## 파일 구조

```
pyproject.toml              의존성, pytest 설정
.gitignore
README.md                   설치·사용법·실측 속도 (Task 12)
install.ps1                 1회 설치: 모델·패키지·Vercel CLI·아이콘·바탕화면 바로가기 (Task 11)
launch.pyw                  바로가기가 pythonw로 실행: Ollama 확인 → 서버 → Edge 앱 창 (Task 11)
assets/ritual-wordmark.png  사용자 로고 원본
office/
  __init__.py               OfficeError, Material, fill(), quiet()
  config.py                 경로·모델·상수
  llm.py                    Ollama: chat, chat_json, is_up, clip
  plan.py                   실장: Plan, normalize_plan, route
  scan.py                   스캐너: load_pages, scan
  literature.py             사서: html_to_text, pick_title, fetch_literature
  note.py                   디자이너: make_note, render_note_html, html_to_pdf, make_pdf
  quiz.py                   출제위원: validate_quiz, make_quiz, render_quiz_html, save_quiz, make_quiz_page
  deploy.py                 배포담당: publish_quiz, write_site_index, parse_deploy_url, deploy_site
  jobs.py                   작업 대기열·직원 상태: Job, Office, merge
  server.py                 FastAPI: create_app, app
  assets.py                 로고 → 픽셀 로고·아이콘
  templates/note.html, quiz.html, site_index.html
web/
  index.html, style.css, app.js, sprites.js
  fonts/Galmuri11.woff2, Galmuri11-Bold.woff2, OFL.txt
  logo-pixel.png, icon.ico     (생성물, git 제외)
tests/
  conftest.py, test_llm.py, test_plan.py, test_scan.py, test_literature.py, test_note.py,
  test_assets.py, test_quiz.py, test_deploy.py, test_jobs.py, test_server.py, test_live.py
  fixtures/wikisource_unsu.html, fixtures/handout.html
```

테스트 실행 명령 (모든 Task 공통):
`$env:UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\ritual-office\venv"; uv run pytest tests/<파일> -v`

---

### Task 1: 뼈대 + Ollama 클라이언트

**Files:**
- Create: `.gitignore`, `pyproject.toml`, `assets/ritual-wordmark.png`, `office/__init__.py`, `office/config.py`, `office/llm.py`
- Test: `tests/test_llm.py`

**Interfaces:**
- Produces:
  - `office.OfficeError(Exception)` — 화면에 그대로 보여줄 한국어 메시지
  - `office.Material` dataclass: `title: str`, `markdown: str`, `sources: list[str] = []`, `original: str | None = None`, `warnings: list[str] = []`
  - `office.fill(name: str, **values: str) -> str` — `office/templates/<name>`을 읽고 `__KEY__`(키를 대문자로)를 값으로 바꾼다
  - `office.quiet(msg: str) -> None` — 아무것도 안 하는 기본 `say`
  - `office.config` 상수 (Step 2)
  - `office.llm.chat(system: str, user: str, *, images: list[bytes] | None = None, schema: dict | None = None, temperature: float = 0.2) -> str`
  - `office.llm.chat_json(system: str, user: str, schema: dict, *, images: list[bytes] | None = None, temperature: float = 0.2) -> dict`
  - `office.llm.is_up() -> bool` (5초 캐시)
  - `office.llm.clip(text: str, limit: int = MAX_INPUT_CHARS) -> str` — 넘치면 앞 `limit`자 + `"\n\n(이하 생략)"`
  - 내부 `office.llm._post(path: str, payload: dict, timeout: float) -> dict` (테스트가 바꿔 끼움)

- [ ] **Step 1: 저장소와 의존성 준비**

```powershell
git init
New-Item -ItemType Directory -Force assets, office\templates, tests\fixtures | Out-Null
Copy-Item 'c:\Users\smile\OneDrive\Desktop\ritual-wordmark-transparent.png' assets\ritual-wordmark.png
```
`.gitignore`: `output/`, `__pycache__/`, `.pytest_cache/`, `.venv/`, `web/logo-pixel.png`, `web/icon.ico`, `*.log`

`pyproject.toml`:
```toml
[project]
name = "ritual-study-office"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["fastapi", "uvicorn", "python-multipart", "pillow", "pypdfium2"]

[dependency-groups]
dev = ["pytest", "httpx"]

[tool.uv]
package = false

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```
Run: `$env:UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\ritual-office\venv"; uv sync`
Expected: 설치 완료, 프로젝트 폴더에 `.venv` 없음. (3.14용 wheel이 없다는 에러가 나면 `uv python pin 3.13` 후 다시)

- [ ] **Step 2: `office/config.py` 작성 (값 그대로)**

```python
ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
WEB = ROOT / "web"
FONTS = WEB / "fonts"
LOGO = ROOT / "assets" / "ritual-wordmark.png"
DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ritual-office"
OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = os.environ.get("RITUAL_MODEL", "qwen3.5:latest")
NUM_CTX = 16384
MAX_INPUT_CHARS = 8000
MAX_IMAGE_SIDE = 1600
MAX_PAGES = 20
HOST, PORT = "127.0.0.1", 8765
BROWSERS = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")]
PALETTE = ["#9337FD", "#E036F0", "#FC34CA", "#FD389C", "#FD633E", "#FC7135"]
GALMURI_CSS = "https://cdn.jsdelivr.net/npm/galmuri@2.40.3/dist/galmuri.css"
```

- [ ] **Step 3: 실패하는 테스트 작성** `tests/test_llm.py`

```python
import base64, io, urllib.error
import pytest
from office import OfficeError
from office import llm

def test_chat_down_raises_korean_hint(monkeypatch):
    monkeypatch.setattr(llm, "OLLAMA_URL", "http://127.0.0.1:9")
    with pytest.raises(OfficeError, match="Ollama"):
        llm.chat("s", "u")

def test_missing_model_hint(monkeypatch):
    def fake_post(path, payload, timeout):
        raise urllib.error.HTTPError("x", 404, "not found", None, io.BytesIO(b'{"error":"model not found"}'))
    monkeypatch.setattr(llm, "_post", fake_post)
    with pytest.raises(OfficeError, match="ollama pull"):
        llm.chat("s", "u")

def test_chat_sends_images_schema_and_no_think(monkeypatch):
    seen = {}
    def fake_post(path, payload, timeout):
        seen.update(path=path, payload=payload)
        return {"message": {"content": "안녕"}}
    monkeypatch.setattr(llm, "_post", fake_post)
    assert llm.chat("sys", "hi", images=[b"\x89PNG"], schema={"type": "object"}) == "안녕"
    p = seen["payload"]
    assert seen["path"] == "/api/chat"
    assert p["messages"][0] == {"role": "system", "content": "sys"}
    assert p["messages"][1]["images"] == [base64.b64encode(b"\x89PNG").decode()]
    assert p["format"] == {"type": "object"} and p["think"] is False and p["stream"] is False
    assert p["options"]["num_ctx"] == 16384 and p["keep_alive"] == "10m"

def test_chat_json_retries_once_then_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "_post", lambda path, payload, timeout: calls.append(1) or {"message": {"content": "{깨진"}})
    with pytest.raises(OfficeError, match="형식"):
        llm.chat_json("s", "u", {"type": "object"})
    assert len(calls) == 2

def test_chat_json_recovers_on_retry(monkeypatch):
    replies = iter(["{깨진", '{"ok": true}'])
    monkeypatch.setattr(llm, "_post", lambda path, payload, timeout: {"message": {"content": next(replies)}})
    assert llm.chat_json("s", "u", {"type": "object"}) == {"ok": True}

def test_clip():
    assert llm.clip("가나다", 10) == "가나다"
    assert llm.clip("가" * 12, 10) == "가" * 10 + "\n\n(이하 생략)"
```

- [ ] **Step 4: 실패 확인** — `tests/test_llm.py` 실행. Expected: FAIL (`ModuleNotFoundError: No module named 'office'`)

- [ ] **Step 5: `office/__init__.py`, `office/llm.py` 구현**
  - `llm.py`는 `from office.config import OLLAMA_URL, MODEL, NUM_CTX, MAX_INPUT_CHARS` 로 가져오고 `_post`가 호출 시점의 모듈 전역 `OLLAMA_URL`을 읽는다 (monkeypatch가 먹도록). `_post`는 `urllib.request`로 JSON POST, timeout 600초.
  - `chat` 안에서 에러를 바꾼다. `HTTPError`가 `URLError`의 하위 클래스이므로 먼저 잡는다: 404 → ``f"모델 {MODEL}이(가) 없어. 터미널에서 `ollama pull {MODEL}` 해줘."``, 그 밖 → `f"Ollama 오류 {code}: {본문 앞 200자}"`. `URLError`·`ConnectionError` → `"Ollama가 꺼져 있어. 작업 표시줄에서 Ollama를 켜줘."` (단 `reason`이 `TimeoutError`면 아래 시간 초과 메시지). `TimeoutError` → `"AI 응답이 10분을 넘겼어. 다시 시도해줘."`
  - `chat_json`: `json.loads` 실패 시 같은 요청을 1회 다시 보내고, 또 실패하면 `OfficeError("AI가 형식에 안 맞는 답을 했어. 다시 시도해줘.")`
  - `is_up`: `GET /api/version`, timeout 2초, 결과를 `time.monotonic()` 기준 5초 캐시.

- [ ] **Step 6: 통과 확인** — Expected: 6 passed

- [ ] **Step 7: 커밋**
```powershell
git add .gitignore pyproject.toml uv.lock assets office tests
git commit -m "chore: scaffold project and ollama client"
```

---

### Task 2: 실장 — 명령 → 작업 순서

**Files:**
- Create: `office/plan.py`
- Test: `tests/test_plan.py`

**Interfaces:**
- Consumes: `office.llm.chat_json`
- Produces:
  - `STEPS = ("scan", "literature", "pdf", "quiz")`
  - `Plan` dataclass: `steps: list[str]`, `title: str = ""`, `work_query: str = ""`, `question_count: int = 10`, `reply: str = ""`, `error: str | None = None`
  - `ROUTER_SCHEMA` — 객체: `steps`(STEPS enum 배열), `title`, `work_query`, `question_count`(integer), `reply`. 전부 required.
  - `normalize_plan(raw: dict, has_files: bool) -> Plan`
  - `route(text: str, has_files: bool, llm=chat_json) -> Plan`

`normalize_plan` 규칙 (이 순서로):
1. `raw["steps"]`가 리스트가 아니면 `[]`. 아는 단계만 남기고 중복 제거, `STEPS` 순서로 정렬.
2. `has_files`면 `"scan"`을 넣고, 아니면 뺀다.
3. `work_query`는 앞뒤 공백 제거. 비었으면 `"literature"`를 뺀다.
4. `question_count`는 int 변환 실패 시 10, 그다음 3~20으로 자른다.
5. `pdf`·`quiz`가 있는데 `scan`·`literature`가 없으면 `error = "자료가 없어. 프린트 사진을 첨부하거나 작품 이름을 알려줘."`
6. `title` = raw title 공백 제거 값, 비었으면 `work_query`.
7. `reply` = raw reply 공백 제거 값. 비었으면 단계가 있을 때 `"알겠어, 시작할게!"`, 없을 때 `"뭘 도와줄까? 프린트를 올리거나 작품 이름을 말해줘."`

`route`의 user 내용은 `f"요청: {text}\n첨부 파일: {'있음' if has_files else '없음'}"`, `temperature=0`. 시스템 지시문 요지: 너는 ritual의 공부 사무실 실장 / 단계 뜻(scan=첨부 읽기, literature=작품 원문·해설 가져오기·work_query에 제목과 아는 작가, pdf=공부 노트 PDF, quiz=문제 웹·question_count 기본 10) / 배포 요청은 단계에 넣지 않음(배포는 사용자가 버튼으로) / reply는 실장 말투 반말 한두 문장.

- [ ] **Step 1: 실패하는 테스트 작성** `tests/test_plan.py`

```python
from office.plan import normalize_plan, route

def test_files_force_scan_first():
    p = normalize_plan({"steps": ["pdf"], "title": "", "work_query": "", "question_count": 10, "reply": ""}, has_files=True)
    assert p.steps == ["scan", "pdf"] and p.error is None and p.reply == "알겠어, 시작할게!"

def test_scan_dropped_without_files_and_asks_for_material():
    p = normalize_plan({"steps": ["scan", "quiz"], "work_query": ""}, has_files=False)
    assert p.steps == ["quiz"] and p.error.startswith("자료가 없어")

def test_literature_needs_query_and_steps_are_ordered():
    p = normalize_plan({"steps": ["quiz", "literature", "quiz"], "work_query": " 운수 좋은 날 "}, has_files=False)
    assert p.steps == ["literature", "quiz"] and p.work_query == "운수 좋은 날" and p.title == "운수 좋은 날"
    assert normalize_plan({"steps": ["literature", "pdf"], "work_query": ""}, has_files=False).error is not None

def test_question_count_clamped_and_garbage_tolerated():
    assert normalize_plan({"steps": ["quiz"], "question_count": 99}, True).question_count == 20
    assert normalize_plan({"steps": ["quiz"], "question_count": "많이"}, True).question_count == 10
    assert normalize_plan({"steps": "pdf", "unknown": 1}, True).steps == ["scan"]

def test_chat_only_keeps_reply():
    p = normalize_plan({"steps": [], "reply": "안녕!"}, False)
    assert p.steps == [] and p.error is None and p.reply == "안녕!"

def test_route_passes_attachment_flag():
    seen = {}
    def fake(system, user, schema, **kw):
        seen["user"] = user
        return {"steps": ["pdf"], "title": "세포", "work_query": "", "question_count": 10, "reply": "PDF로 만들게"}
    p = route("이거 PDF로", has_files=True, llm=fake)
    assert "첨부 파일: 있음" in seen["user"] and p.steps == ["scan", "pdf"] and p.title == "세포"
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL (`No module named 'office.plan'`)
- [ ] **Step 3: `office/plan.py` 구현** (위 규칙 그대로)
- [ ] **Step 4: 통과 확인** — Expected: 6 passed
- [ ] **Step 5: 커밋** — `git add office/plan.py tests/test_plan.py` → `feat: add manager router`

---

### Task 3: 스캐너 — 사진·PDF → 글자

**Files:**
- Create: `office/scan.py`
- Test: `tests/test_scan.py`

**Interfaces:**
- Consumes: `office.llm.chat`, `office.Material`, `office.OfficeError`, `office.quiet`, `config.MAX_IMAGE_SIDE`, `config.MAX_PAGES`, `config.MAX_INPUT_CHARS`
- Produces:
  - `IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}`
  - `load_pages(path: Path) -> list[bytes | str]` — bytes는 정규화한 JPEG, str은 PDF에 들어 있던 글자
  - `scan(files: list[Path], llm=chat, say=quiet) -> Material`

동작:
- 이미지: `ImageOps.exif_transpose` → `convert("RGB")` → `thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))` → JPEG quality 90 bytes.
- PDF(pypdfium2): 쪽 수 > `MAX_PAGES`면 `OfficeError(f"PDF가 {n}쪽이야. {MAX_PAGES}쪽까지만 돼. 나눠서 올려줘.")`. 쪽마다 `page.get_textpage().get_text_range().strip()`이 50자 이상이면 그 글자, 아니면 `page.render(scale=2).to_pil()`을 이미지처럼 정규화.
- 그 밖 확장자: `OfficeError("JPG·PNG·WEBP·PDF만 읽을 수 있어. 아이폰 사진은 설정 > 카메라 > 포맷 > '높은 호환성'으로 찍어줘.")`
- `scan`: 전체 쪽 수가 `MAX_PAGES`를 넘으면 `OfficeError(f"사진·쪽이 모두 {n}장이야. {MAX_PAGES}장까지만 돼.")`. 쪽마다 `say(f"{i}/{n}쪽 읽는 중")`. 이미지 쪽은 `llm(OCR_SYSTEM, "이 프린트를 마크다운으로 옮겨줘.", images=[page], temperature=0)`. 쪽 결과는 `"\n\n---\n\n"`로 잇는다. 제목은 첫 `# ` 줄, 없으면 `files[0].stem`. `sources`는 파일 이름들. 본문이 `MAX_INPUT_CHARS`보다 길면 `warnings`에 `f"자료가 길어서({길이}자) 앞 {MAX_INPUT_CHARS}자만 정리에 써."`
- `OCR_SYSTEM` 요지: 너는 스캐너 직원 / 사진 속 프린트 글자를 빠짐없이 그대로 마크다운으로 / 제목 `#`, 소제목 `##`, 목록 `-`, 표는 마크다운 표 / 사진에 없는 내용 절대 금지 / 설명·인사 없이 옮긴 내용만.

- [ ] **Step 1: 실패하는 테스트 작성** `tests/test_scan.py`

```python
import io
import pytest
from PIL import Image
from office import OfficeError
from office.config import MAX_IMAGE_SIDE, MAX_PAGES, MAX_INPUT_CHARS
from office.scan import load_pages, scan

def _text_pdf(path):
    stream = b"BT /F1 12 Tf 50 800 Td (This handout has a real text layer so no OCR is needed here.) Tj ET"
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>",
            b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
            b"<</Length %d>>stream\n" % len(stream) + stream + b"\nendstream"]
    body = b"%PDF-1.4\n" + b"".join(b"%d 0 obj\n" % (i + 1) + o + b"\nendobj\n" for i, o in enumerate(objs))
    path.write_bytes(body + b"trailer<</Root 1 0 R>>\n%%EOF\n")   # xref 없음: pdfium이 복구해서 읽음

def test_exif_rotated_photo_is_upright(tmp_path):
    p = tmp_path / "photo.jpg"
    exif = Image.Exif(); exif[0x0112] = 6
    Image.new("RGB", (200, 100), "white").save(p, "JPEG", exif=exif)
    [page] = load_pages(p)
    assert Image.open(io.BytesIO(page)).size == (100, 200)

def test_big_photo_is_shrunk(tmp_path):
    p = tmp_path / "big.png"; Image.new("RGB", (4000, 3000)).save(p)
    [page] = load_pages(p)
    assert max(Image.open(io.BytesIO(page)).size) == MAX_IMAGE_SIDE

def test_heic_is_rejected_with_hint(tmp_path):
    p = tmp_path / "a.heic"; p.write_bytes(b"x")
    with pytest.raises(OfficeError, match="JPG"):
        load_pages(p)

def test_image_only_pdf_becomes_image(tmp_path):
    p = tmp_path / "scan.pdf"; Image.new("RGB", (595, 842), "white").save(p)
    [page] = load_pages(p)
    assert isinstance(page, bytes)

def test_text_pdf_uses_text_layer(tmp_path):
    p = tmp_path / "digital.pdf"; _text_pdf(p)
    [page] = load_pages(p)
    assert isinstance(page, str) and "real text layer" in page

def test_too_many_pages(tmp_path):
    p = tmp_path / "long.pdf"
    pages = [Image.new("RGB", (100, 100)) for _ in range(MAX_PAGES + 1)]
    pages[0].save(p, save_all=True, append_images=pages[1:])
    with pytest.raises(OfficeError, match=str(MAX_PAGES)):
        load_pages(p)

def test_scan_joins_pages_and_takes_title(tmp_path):
    a, b = tmp_path / "1.png", tmp_path / "2.png"
    Image.new("RGB", (50, 50)).save(a); Image.new("RGB", (50, 50)).save(b)
    replies = iter(["# 세포의 구조\n- 핵", "## 세포막\n- 선택적 투과"])
    m = scan([a, b], llm=lambda system, user, **kw: next(replies))
    assert m.title == "세포의 구조" and m.sources == ["1.png", "2.png"]
    assert m.markdown == "# 세포의 구조\n- 핵\n\n---\n\n## 세포막\n- 선택적 투과" and m.warnings == []

def test_long_material_warns(tmp_path):
    a = tmp_path / "1.png"; Image.new("RGB", (50, 50)).save(a)
    m = scan([a], llm=lambda system, user, **kw: "가" * (MAX_INPUT_CHARS + 1))
    assert "앞 8000자만" in m.warnings[0]
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL (`No module named 'office.scan'`)
- [ ] **Step 3: `office/scan.py` 구현**
- [ ] **Step 4: 통과 확인** — Expected: 8 passed. (`_text_pdf`를 pdfium이 못 읽으면 테스트 헬퍼에 xref 표를 추가한다. 구현은 고치지 않는다.)
- [ ] **Step 5: 커밋** — `git add office/scan.py tests/test_scan.py` → `feat: add scanner (photos and pdf to text)`

---

### Task 4: 사서 — 문학 작품 가져오기

**Files:**
- Create: `office/literature.py`, `tests/fixtures/wikisource_unsu.html`
- Test: `tests/test_literature.py`

**Interfaces:**
- Consumes: `office.llm.chat`, `office.llm.clip`, `office.Material`, `office.OfficeError`, `office.quiet`
- Produces:
  - `WIKISOURCE = "ko.wikisource.org"`, `WIKIPEDIA = "ko.wikipedia.org"`, `UA = "RitualStudyOffice/0.1 (personal study tool)"`
  - `_get_json(host: str, params: dict) -> dict` — `https://{host}/w/api.php`, `format=json`·`formatversion=2`를 붙이고 UA 헤더, timeout 20초. 네트워크 실패는 `OfficeError("인터넷 연결을 확인해줘. (위키 접속 실패)")`
  - `html_to_text(html: str) -> str`
  - `pick_title(query: str, titles: list[str]) -> str | None`
  - `page_url(host: str, title: str) -> str` — `f"https://{host}/wiki/{quote(title.replace(' ', '_'))}"`
  - `fetch_literature(query: str, llm=chat, get_json=_get_json, say=quiet) -> Material`

동작:
- `html_to_text`: `html.parser` 기반. `style`·`script` 태그와 class에 `ws-noexport`, `noprint`, `mw-editsection`, `licenseContainer`, `licensetpl` 중 하나라도 있는 요소는 하위까지 통째로 건너뛴다 (void 태그 `br` 등은 깊이 계산에서 뺀다). `p div br li h1~h6 tr dd dt`에서 줄을 바꾼다. 줄마다 strip, 글자·숫자가 하나도 없는 줄(장식 기호 `🙝🙟` 등)은 버리고, 3줄 이상 빈 줄은 2줄로 줄인다. 끝에 남은 위키문헌 라이선스 제목 `"라이선스"`는 뗀다.
- `pick_title`: 공백 제거·소문자로 비교. 정규화한 query가 제목에 들어 있거나, 정규화한 제목(2글자 이상)이 query에 들어 있는 첫 제목. 없으면 `None`.
- `fetch_literature`:
  1. `say("위키문헌에서 원문 찾는 중")` → 위키문헌 검색(`action=query&list=search&srsearch=<query>&srlimit=5`) → `pick_title` → 있으면 `action=parse&page=<제목>&prop=text&redirects=1` 의 `parse.text` → `html_to_text` = 원문.
  2. `say("위키백과에서 해설 자료 찾는 중")` → 위키백과 검색 → `pick_title` → 있으면 `action=query&prop=extracts&explaintext=1&redirects=1&titles=<제목>` 의 `query.pages[0].extract`.
  3. 둘 다 없으면 `OfficeError(f"'{query}'을(를) 못 찾았어. 작가 이름도 같이 써줘.")`
  4. `say("공부 노트 쓰는 중")` → `llm(LIB_SYSTEM, f"작품: {제목}\n\n[해설 자료]\n{clip(해설, 4000)}\n\n[원문 앞부분]\n{clip(원문, 4000) 또는 '(원문 없음: 저작권 보호 작품일 수 있음)'}", temperature=0.2)` → `markdown`.
  5. `Material(title=위키문헌 제목 or 위키백과 제목, markdown=노트, sources=[찾은 페이지 URL들, 위키문헌 먼저], original=원문 or None)`. 원문이 없으면 `warnings`에 `"위키문헌에 원문이 없어(저작권 보호 작품일 수 있음) 해설만 정리했어."`
- `LIB_SYSTEM` 요지: 너는 사서 직원 / 주어진 자료만 근거로 학생용 공부 노트를 마크다운으로 / 항목 `## 작품 정보`(작가·갈래·시대), `## 내용 정리`, `## 주제`, `## 표현상 특징`, `## 감상 포인트` / 자료에 없으면 "자료에 없음".

- [ ] **Step 1: 실패하는 테스트 작성** `tests/test_literature.py`

```python
from pathlib import Path
from urllib.parse import unquote
import pytest
from office import OfficeError
from office.literature import WIKISOURCE, html_to_text, pick_title, fetch_literature

FIXTURE = Path(__file__).parent / "fixtures" / "wikisource_unsu.html"

def test_html_to_text_on_real_page():
    text = html_to_text(FIXTURE.read_text(encoding="utf-8"))
    assert text.startswith("새침하게 흐린 품이")
    assert text.endswith("”") and "라이선스" not in text[-50:]
    assert "{" not in text and len(text) > 5000

def test_html_to_text_keeps_poem_lines():
    html = '<div class="ws-noexport">머리말</div><div class="poem"><p>나 보기가 역겨워<br>가실 때에는<br></p></div>'
    assert html_to_text(html) == "나 보기가 역겨워\n가실 때에는"

def test_pick_title():
    assert pick_title("운수 좋은 날", ["운수 좋은 날", "서울특별시 택시운수종사자 복지시설"]) == "운수 좋은 날"
    assert pick_title("운수 좋은 날 현진건", ["운수 좋은 날"]) == "운수 좋은 날"
    assert pick_title("소나기", ["서울특별시 조례"]) is None

def fake_get_json(source=True, wiki=True):
    def get(host, params):
        if params.get("list") == "search":
            found = source if host == WIKISOURCE else wiki
            return {"query": {"search": [{"title": "운수 좋은 날"}] if found else []}}
        if params.get("action") == "parse":
            return {"parse": {"text": "<p>새침하게 흐린 품이 눈이 올 듯하더니</p>"}}
        return {"query": {"pages": [{"extract": "현진건의 단편소설이다."}]}}
    return get

def test_public_domain_work_keeps_original():
    seen = {}
    def llm(system, user, **kw):
        seen["user"] = user
        return "## 작품 정보\n현진건"
    m = fetch_literature("운수 좋은 날", llm=llm, get_json=fake_get_json())
    assert m.original.startswith("새침하게") and "현진건의 단편소설" in seen["user"]
    assert unquote(m.sources[0]) == "https://ko.wikisource.org/wiki/운수_좋은_날"
    assert unquote(m.sources[1]) == "https://ko.wikipedia.org/wiki/운수_좋은_날"
    assert m.markdown == "## 작품 정보\n현진건" and m.warnings == []

def test_copyrighted_work_has_no_original():
    m = fetch_literature("운수 좋은 날", llm=lambda s, u, **k: "노트", get_json=fake_get_json(source=False))
    assert m.original is None and "저작권" in m.warnings[0]

def test_nothing_found():
    with pytest.raises(OfficeError, match="작가"):
        fetch_literature("없는작품", llm=lambda s, u, **k: "", get_json=fake_get_json(False, False))
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL (`No module named 'office.literature'`)
- [ ] **Step 3: `office/literature.py` 구현**
- [ ] **Step 4: 실제 페이지로 fixture 저장 (1회)**
```powershell
$env:UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\ritual-office\venv"; uv run python -c "from pathlib import Path; from office.literature import _get_json, WIKISOURCE; Path('tests/fixtures/wikisource_unsu.html').write_text(_get_json(WIKISOURCE, {'action': 'parse', 'page': '운수 좋은 날', 'prop': 'text', 'redirects': 1})['parse']['text'], encoding='utf-8')"
```
Expected: 약 24KB 파일 생성
- [ ] **Step 5: 통과 확인** — Expected: 6 passed
- [ ] **Step 6: 커밋** — `git add office/literature.py tests/test_literature.py tests/fixtures/wikisource_unsu.html` → `feat: add librarian (wikisource and wikipedia)`

---

### Task 5: 디자이너 — 노트 PDF + 픽셀 폰트·로고

**Files:**
- Create: `office/note.py`, `office/templates/note.html`, `office/assets.py`, `web/fonts/Galmuri11.woff2`, `web/fonts/Galmuri11-Bold.woff2`, `web/fonts/OFL.txt`
- Test: `tests/test_note.py`, `tests/test_assets.py`

**Interfaces:**
- Consumes: `office.llm.chat_json`, `office.llm.clip`, `office.Material`, `office.OfficeError`, `office.fill`, `office.quiet`, `config.BROWSERS`, `config.DATA`, `config.FONTS`, `config.WEB`, `config.PALETTE`, `config.LOGO`
- Produces:
  - `NOTE_SCHEMA` — `title`, `subtitle`, `sections[{heading, points[str], highlight}]`, `key_terms[{term, meaning}]`, `summary[str]` (전부 required)
  - `make_note(material: Material, llm=chat_json) -> dict`
  - `render_note_html(note: dict, material: Material) -> str`
  - `html_to_pdf(html_path: Path, pdf_path: Path) -> None`
  - `make_pdf(material: Material, job_dir: Path, llm=chat_json, say=quiet) -> Path` — `job_dir/note.html`, `job_dir/note.pdf`를 만들고 pdf 경로를 돌려준다
  - `office.assets.build_pixel_logo(src: Path, out: Path, width: int = 128, scale: int = 3) -> None`

동작:
- `make_note`: `llm(NOTE_SYSTEM, clip(material.markdown), NOTE_SCHEMA, temperature=0.2)`. `sections`가 비면 `OfficeError("정리할 내용이 없어.")`. `NOTE_SYSTEM` 요지: 너는 디자이너 직원 / 자료를 공부 노트 구조로 재배치 / 자료 내용은 빠뜨리지 말고 없는 내용은 추가 금지 / sections는 자료 흐름 순서, points는 짧은 문장, highlight는 섹션 핵심 한 문장(없으면 빈 문자열), key_terms는 자료에 나온 용어만, summary 3~5줄.
- `note.html` 템플릿 자리표시자: `__TITLE__ __SUBTITLE__ __BAR__ __SECTIONS__ __TERMS__ __SUMMARY__ __ORIGINAL__ __FOOTER__ __FONT_REGULAR__ __FONT_BOLD__`. 모든 글자는 `html.escape`.
  - `@page { size: A4; margin: 14mm 14mm 18mm }`, 본문 `"Malgun Gothic"` 10.5pt / line-height 1.65 / `#1d1b26`. 제목·섹션 제목·라벨은 Galmuri11(`@font-face`, src는 `FONTS / 파일`의 `as_uri()`), 제목 22pt Bold.
  - `__BAR__`: PALETTE 6칸 픽셀 띠 (높이 8px).
  - 섹션 제목 앞 8px 정사각 블록(PALETTE 순환), 핵심 문장 박스는 `border: 2px solid #1d1b26; box-shadow: 4px 4px 0 <섹션 색>`.
  - 용어 표, "한눈에 정리" 박스.
  - `material.original`이 있을 때만 `<section class="original">` (새 쪽에서 시작, `white-space: pre-wrap`, 제목 "원문").
  - 바닥글(`position: fixed; bottom`): `WEB/logo-pixel.png`가 있으면 그 이미지(높이 14px), "ritual의 공부 사무실 · YYYY-MM-DD", 출처 목록.
- `html_to_pdf`: `BROWSERS` 중 있는 첫 브라우저, 없으면 `OfficeError("PDF를 만들려면 Edge나 Chrome이 필요해.")`. 인자 `[browser, "--headless", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer", f"--user-data-dir={DATA / 'edge-headless'}", f"--print-to-pdf={pdf_path}", html_path.as_uri()]`, timeout 90초. 결과 파일이 없거나 `%PDF`로 시작하지 않으면 `OfficeError("PDF 만들기 실패: " + stderr 마지막 줄)`. (`--user-data-dir`를 따로 둬야 이미 켜진 Edge에 붙지 않는다.)
- `make_pdf`: `say("노트 구조 잡는 중")` → `make_note` → `note.html` 저장(UTF-8) → `say("PDF 인쇄 중")` → `html_to_pdf` → pdf 경로.
- `build_pixel_logo`: RGBA로 열고 알파 bbox로 자름 → 너비 `width`로 LANCZOS 축소 → 알파를 128 기준 0/255로 → `scale`배 NEAREST 확대 → PNG.

- [ ] **Step 1: 폰트 받기**
```powershell
New-Item -ItemType Directory -Force web\fonts | Out-Null
foreach ($f in 'Galmuri11.woff2', 'Galmuri11-Bold.woff2') { Invoke-WebRequest "https://cdn.jsdelivr.net/npm/galmuri@2.40.3/dist/$f" -OutFile "web\fonts\$f" }
Invoke-WebRequest 'https://cdn.jsdelivr.net/npm/galmuri@2.40.3/dist/LICENSE.txt' -OutFile web\fonts\OFL.txt
```

- [ ] **Step 2: 실패하는 테스트 작성** `tests/test_note.py`, `tests/test_assets.py`

```python
# tests/test_note.py
import pytest
from office import Material, OfficeError
from office.config import BROWSERS
from office.note import make_note, render_note_html, html_to_pdf

SAMPLE_NOTE = {"title": "세포의 구조", "subtitle": "생명과학 1단원",
               "sections": [{"heading": "핵", "points": ["유전 물질 보관", "<script>alert(1)</script>"], "highlight": "핵 = 세포의 사령부"}],
               "key_terms": [{"term": "핵막", "meaning": "핵을 감싸는 막"}], "summary": ["세포는 생명의 기본 단위"]}

def test_note_html_escapes_and_contains_content():
    html = render_note_html(SAMPLE_NOTE, Material(title="세포의 구조", markdown="", sources=["1.jpg"]))
    for text in ["세포의 구조", "핵 = 세포의 사령부", "핵막", "세포는 생명의 기본 단위", "1.jpg"]:
        assert text in html
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html

def test_original_section_only_when_present():
    with_original = render_note_html(SAMPLE_NOTE, Material(title="t", markdown="", original="새침하게 흐린 품이"))
    assert 'class="original"' in with_original and "새침하게 흐린 품이" in with_original
    assert 'class="original"' not in render_note_html(SAMPLE_NOTE, Material(title="t", markdown=""))

def test_make_note_rejects_empty():
    empty = {"title": "t", "subtitle": "", "sections": [], "key_terms": [], "summary": []}
    with pytest.raises(OfficeError):
        make_note(Material(title="t", markdown="x"), llm=lambda *a, **k: empty)

@pytest.mark.skipif(not any(p.exists() for p in BROWSERS), reason="Edge/Chrome 없음")
def test_pdf_has_korean_fonts(tmp_path):
    folder = tmp_path / "한글 폴더"; folder.mkdir()
    html = folder / "note.html"
    html.write_text(render_note_html(SAMPLE_NOTE, Material(title="세포의 구조", markdown="")), encoding="utf-8")
    pdf = folder / "note.pdf"
    html_to_pdf(html, pdf)
    data = pdf.read_bytes()
    assert data[:4] == b"%PDF" and b"Galmuri" in data and b"Malgun" in data
```

```python
# tests/test_assets.py
from PIL import Image
from office.assets import build_pixel_logo
from office.config import LOGO

def test_pixel_logo_is_crisp(tmp_path):
    out = tmp_path / "logo.png"
    build_pixel_logo(LOGO, out, width=64, scale=3)
    img = Image.open(out).convert("RGBA")
    assert img.width == 192 and img.height % 3 == 0
    assert set(img.getchannel("A").getdata()) <= {0, 255}
```

- [ ] **Step 3: 실패 확인** — `tests/test_note.py tests/test_assets.py`. Expected: FAIL (모듈 없음)
- [ ] **Step 4: `office/assets.py`(build_pixel_logo), `office/note.py`, `office/templates/note.html` 구현**
- [ ] **Step 5: 통과 확인** — Expected: 5 passed
- [ ] **Step 6: 눈으로 확인**
```powershell
$env:UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\ritual-office\venv"; uv run python -c "from office.assets import build_pixel_logo; from office.config import LOGO, WEB; build_pixel_logo(LOGO, WEB / 'logo-pixel.png')"
```
그다음 `tests/test_note.py`의 `SAMPLE_NOTE`로 `output/sample/note.pdf`를 만들고 `pypdfium2`로 1쪽을 PNG(`render(scale=1.5)`)로 저장해 Read로 본다. 확인: 픽셀 로고·6색 띠·Galmuri 제목·맑은 고딕 본문, 글자 깨짐 없음. 어색하면 템플릿 CSS만 고친다.
- [ ] **Step 7: 커밋** — `git add office/note.py office/assets.py office/templates/note.html web/fonts tests/test_note.py tests/test_assets.py` → `feat: add designer (study note pdf) and pixel assets`

---

### Task 6: 출제위원 — 문제 + 문제 풀이 페이지

**Files:**
- Create: `office/quiz.py`, `office/templates/quiz.html`
- Test: `tests/test_quiz.py`

**Interfaces:**
- Consumes: `office.llm.chat_json`, `office.llm.clip`, `office.Material`, `office.OfficeError`, `office.fill`, `office.quiet`, `config.GALMURI_CSS`
- Produces:
  - `QUIZ_SCHEMA` — `title`, `questions[{kind: "mc"|"ox"|"short", question, choices[str], answer: str, explanation}]` (전부 required)
  - `validate_quiz(raw: dict) -> dict` — 결과 `{"title": str, "questions": [{"kind", "question", "choices", "answer", "explanation"}]}`, mc의 `answer`는 int(0~3), ox는 `"O"`/`"X"`, short는 문자열
  - `make_quiz(material: Material, count: int, llm=chat_json) -> dict`
  - `render_quiz_html(quiz: dict) -> str` — CSS·JS가 안에 다 들어간 한 파일 페이지
  - `save_quiz(job_dir: Path, quiz: dict) -> Path` — `job_dir/quiz/index.html`, `job_dir/quiz/quiz.json` 저장, index 경로 반환
  - `make_quiz_page(material: Material, count: int, job_dir: Path, llm=chat_json, say=quiet) -> Path`

동작:
- `validate_quiz`: 질문이 비었거나 이미 나온 질문이면 버림. mc는 보기 정확히 4개(공백 제거 후 비지 않음)이고 정답이 보기 문장과 같거나 `"1"~"4"`, `"①"~"④"`, `"A"~"D"`(대소문자 무시)면 인덱스로, 아니면 버림. ox는 `O/o/○/⭕/참/맞음/true`→`"O"`, `X/x/×/❌/거짓/틀림/false`→`"X"`, 아니면 버림(choices는 `[]`). short는 정답이 비지 않아야 함(choices `[]`). 남은 문제가 3개 미만이면 `OfficeError("쓸 만한 문제가 3개도 안 나왔어. 다시 시도해줘.")`. 제목이 비면 `"문제"`.
- `make_quiz`: 재료 = `material.markdown` + (원문 있으면 `"\n\n[원문]\n" + original`). user = `f"문제 수: {count}\n\n{clip(재료)}"`, `temperature=0.3`. `validate_quiz`가 `OfficeError`면 1회 다시 요청, 또 실패하면 그 에러를 그대로 올림. 문제는 `count`개까지 자른다. `QUIZ_SYSTEM` 요지: 너는 출제위원 직원 / 자료 내용으로만 / mc는 보기 4개와 정답 보기 문장 그대로, ox는 O 또는 X, short는 짧은 정답 / 모든 문제에 해설 / 자료에 없는 사실 금지 / 객관식 위주로 섞기.
- `render_quiz_html`: 템플릿 자리표시자 `__TITLE__`(escape), `__GALMURI_CSS__`, `__QUIZ_JSON__`. 데이터는 `<script id="quiz-data" type="application/json">` 안에 `json.dumps(quiz, ensure_ascii=False).replace("<", "\\u003c")`.
- 문제 페이지 동작 (바닐라 JS, 외부 JS 없음): 한 문제씩, "3 / 10" + PALETTE 블록 진행 막대 / mc는 보기 버튼 4개, ox는 O·X 버튼, short는 입력칸 + [확인](공백 제거·소문자로 비교) / 답하면 정답·오답 + 해설 + [다음] / 끝나면 점수, 틀린 문제 다시 보기, [다시 풀기] / 바닥글 "ritual의 공부 사무실에서 만듦". 디자인은 Global Constraints의 픽셀 규칙, 어두운 바탕, 휴대폰 너비에서도 깨지지 않게.
- `make_quiz_page`: `say(f"문제 {count}개 내는 중")` → `make_quiz` → `say(f"{n}문제 완성")` → `save_quiz`.

- [ ] **Step 1: 실패하는 테스트 작성** `tests/test_quiz.py`

```python
import json
import pytest
from office import Material, OfficeError
from office.quiz import validate_quiz, make_quiz, render_quiz_html, save_quiz

RAW = {"title": "세포 퀴즈", "questions": [
    {"kind": "mc", "question": "세포의 사령부는?", "choices": ["핵", "세포막", "리보솜", "액포"], "answer": "핵", "explanation": "핵에 DNA가 있다"},
    {"kind": "mc", "question": "단백질 합성 장소는?", "choices": ["핵", "세포막", "리보솜", "액포"], "answer": "③", "explanation": ""},
    {"kind": "mc", "question": "보기 3개짜리", "choices": ["a", "b", "c"], "answer": "a", "explanation": ""},
    {"kind": "ox", "question": "세포막은 선택적 투과성이 있다", "choices": [], "answer": "o", "explanation": ""},
    {"kind": "short", "question": "식물 세포에만 있는 벽은?", "choices": [], "answer": "세포벽", "explanation": ""},
    {"kind": "ox", "question": "세포막은 선택적 투과성이 있다", "choices": [], "answer": "O", "explanation": ""},
    {"kind": "mc", "question": "정답이 보기에 없음", "choices": ["a", "b", "c", "d"], "answer": "z", "explanation": ""}]}

def test_validate_quiz_normalizes_and_drops_bad():
    q = validate_quiz(RAW)["questions"]
    assert [x["question"] for x in q] == ["세포의 사령부는?", "단백질 합성 장소는?", "세포막은 선택적 투과성이 있다", "식물 세포에만 있는 벽은?"]
    assert q[0]["answer"] == 0 and q[1]["answer"] == 2 and q[2]["answer"] == "O" and q[3]["answer"] == "세포벽"

def test_validate_quiz_too_few():
    with pytest.raises(OfficeError, match="3개"):
        validate_quiz({"title": "t", "questions": RAW["questions"][:2]})

def test_make_quiz_retries_once_then_caps_count():
    calls = []
    def llm(system, user, schema, **kw):
        calls.append(user)
        return {"title": "t", "questions": []} if len(calls) == 1 else RAW
    quiz = make_quiz(Material(title="세포", markdown="세포 자료"), count=3, llm=llm)
    assert len(calls) == 2 and len(quiz["questions"]) == 3 and "문제 수: 3" in calls[0]

def test_quiz_html_survives_script_injection():
    quiz = validate_quiz(RAW)
    quiz["questions"][0]["question"] = "</script><script>alert(1)</script>"
    html = render_quiz_html(quiz)
    assert html.count("</script>") == html.count("<script")
    data = html.split('<script id="quiz-data" type="application/json">')[1].split("</script>")[0]
    assert json.loads(data) == quiz

def test_save_quiz_writes_page_and_json(tmp_path):
    index = save_quiz(tmp_path, validate_quiz(RAW))
    assert index == tmp_path / "quiz" / "index.html" and index.exists()
    assert json.loads((tmp_path / "quiz" / "quiz.json").read_text(encoding="utf-8"))["title"] == "세포 퀴즈"
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL (`No module named 'office.quiz'`)
- [ ] **Step 3: `office/quiz.py`, `office/templates/quiz.html` 구현**
- [ ] **Step 4: 통과 확인** — Expected: 5 passed
- [ ] **Step 5: 눈으로 확인** — `RAW`로 `output/sample/quiz/index.html`을 만들고 Edge headless `--screenshot`(1440×900, 그리고 390×844)으로 찍어 Read로 본다. 첫 문제 화면이 픽셀 스타일이고 한글이 Galmuri로 보이면 통과.
- [ ] **Step 6: 커밋** — `git add office/quiz.py office/templates/quiz.html tests/test_quiz.py` → `feat: add examiner (quiz page)`

---

### Task 7: 배포담당 — 문제 사이트 → Vercel

**Files:**
- Create: `office/deploy.py`, `office/templates/site_index.html`
- Test: `tests/test_deploy.py`

**Interfaces:**
- Consumes: `office.quiz.save_quiz`, `office.quiz.validate_quiz`(테스트), `office.fill`, `office.OfficeError`, `config.GALMURI_CSS`
- Produces:
  - `publish_quiz(job_dir: Path, slug: str, site_dir: Path) -> None` — `job_dir/quiz`를 `site_dir/q/<slug>`로 복사(`dirs_exist_ok=True`) 후 `write_site_index`
  - `write_site_index(site_dir: Path) -> None` — `site_dir/q/*/quiz.json` 제목으로 목록 페이지 `site_dir/index.html` (slug 내림차순 = 최신순, 링크 `q/<slug>/`, 제목 escape)
  - `parse_deploy_url(stdout: str, stderr: str) -> str`
  - `deploy_site(site_dir: Path, run=subprocess.run) -> str` — 공개 기본 주소 반환 (끝에 `/` 없음)

동작:
- `parse_deploy_url`: 두 출력에서 `https://[a-z0-9.-]+\.vercel\.app`을 모두 찾아 가장 짧은 것(= 프로젝트 기본 주소. 배포별 주소는 로그인 벽이 있음). 하나도 없으면 `OfficeError("배포 주소를 못 찾았어.")`.
- `deploy_site`: `shutil.which("vercel")`가 없으면 `OfficeError("Vercel CLI가 없어. 터미널에서 npm i -g vercel 하고 vercel login 해줘.")`. `run([vercel, "deploy", "--prod", "--yes"], cwd=site_dir, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)`. 실패(returncode≠0)면 stderr에 `login` 또는 `credentials`가 있을 때 `OfficeError("Vercel 로그인이 필요해. 터미널에서 vercel login 해줘.")`, 아니면 `OfficeError("배포 실패: " + stderr 마지막 줄)`. 성공이면 `parse_deploy_url`.
- 사이트 폴더 이름이 Vercel 프로젝트 이름이 된다: `site_dir`은 `output/ritual-quiz` (Task 8에서 고정).

- [ ] **Step 1: 실패하는 테스트 작성** `tests/test_deploy.py`

```python
import shutil, subprocess
import pytest
from office import OfficeError
from office.deploy import parse_deploy_url, deploy_site, publish_quiz
from office.quiz import save_quiz, validate_quiz
from test_quiz import RAW

ERR = ("🔍  Inspect: https://vercel.com/ritual/ritual-quiz/AbC [2s]\n"
       "✅  Production: https://ritual-quiz-k2j3h4-ritual.vercel.app [2s]\n"
       "🔗  Aliased: https://ritual-quiz.vercel.app [2s]\n")

def test_parse_prefers_short_alias():
    assert parse_deploy_url("https://ritual-quiz-k2j3h4-ritual.vercel.app\n", ERR) == "https://ritual-quiz.vercel.app"

def test_parse_without_urls():
    with pytest.raises(OfficeError):
        parse_deploy_url("", "Error: something")

def test_deploy_without_cli(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(OfficeError, match="npm i -g vercel"):
        deploy_site(tmp_path)

def test_deploy_login_error(monkeypatch, tmp_path):
    monkeypatch.setattr(shutil, "which", lambda name: "vercel.cmd")
    fake = lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "Error: No existing credentials found. Please run `vercel login`")
    with pytest.raises(OfficeError, match="vercel login"):
        deploy_site(tmp_path, run=fake)

def test_deploy_success_runs_prod(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(shutil, "which", lambda name: "vercel.cmd")
    def fake(cmd, **kw):
        seen.update(cmd=cmd, cwd=kw["cwd"])
        return subprocess.CompletedProcess(cmd, 0, "https://ritual-quiz-k2j3h4-ritual.vercel.app\n", ERR)
    assert deploy_site(tmp_path, run=fake) == "https://ritual-quiz.vercel.app"
    assert seen["cmd"] == ["vercel.cmd", "deploy", "--prod", "--yes"] and seen["cwd"] == tmp_path

def test_publish_copies_quiz_and_lists_it(tmp_path):
    job = tmp_path / "jobs" / "j1"
    save_quiz(job, validate_quiz(RAW))
    site = tmp_path / "ritual-quiz"
    publish_quiz(job, "j1", site)
    assert (site / "q" / "j1" / "index.html").exists()
    index = (site / "index.html").read_text(encoding="utf-8")
    assert 'href="q/j1/"' in index and "세포 퀴즈" in index
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL (`No module named 'office.deploy'`)
- [ ] **Step 3: `office/deploy.py`, `office/templates/site_index.html` 구현** (목록 페이지도 픽셀 스타일, 제목 "ritual의 문제 모음")
- [ ] **Step 4: 통과 확인** — Expected: 6 passed
- [ ] **Step 5: 커밋** — `git add office/deploy.py office/templates/site_index.html tests/test_deploy.py` → `feat: add deployer (vercel)`

---

### Task 8: 작업 대기열과 직원 상태

**Files:**
- Create: `office/jobs.py`, `tests/conftest.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `office.plan.route`, `office.plan.Plan`, `office.scan.scan`, `office.literature.fetch_literature`, `office.note.make_pdf`, `office.quiz.make_quiz_page`, `office.deploy.publish_quiz`, `office.deploy.deploy_site`, `office.Material`, `office.OfficeError`, `config.OUTPUT`
- Produces:
  - `ROLES = {"manager": "실장", "scanner": "스캐너", "librarian": "사서", "designer": "디자이너", "examiner": "출제위원", "deployer": "배포담당"}`
  - `Job` dataclass: `id: str`, `text: str`, `files: list[str]`, `status: str = "queued"`(queued | running | done | error | needs_input), `title: str = ""`, `reply: str = ""`, `error: str | None = None`, `log: list[str]`, `results: dict`(키 `pdf`, `quiz`, `text` = `/files/...` 주소, `deploy_url`, `deploy_error`), `warnings: list[str]`, `created: str`(`"2026-10-21 15:30"`)
  - `Office(root: Path = OUTPUT, *, route=route, steps: dict | None = None, deploy=deploy_site)` — `self.root`, `self.jobs_dir = root/"jobs"`, `self.site_dir = root/"ritual-quiz"`, 생성 시 `jobs_dir` 생성. `steps` 기본값 `{"scan": scan, "literature": fetch_literature, "pdf": make_pdf, "quiz": make_quiz_page}`
    - `new_job_dir() -> tuple[str, Path]` — id `f"{%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"`, `jobs_dir/id/inputs` 생성
    - `submit(job_id: str, text: str, files: list[Path]) -> None`
    - `submit_deploy(job_id: str) -> None` — 없는 id면 `OfficeError("그런 작업이 없어.")`, `results`에 `quiz`가 없으면 `OfficeError("배포할 문제 웹이 없어.")`
    - `run_next(block: bool = False) -> bool` — 대기열에서 하나 처리, 비었으면 `False`
    - `start() -> None` — 데몬 스레드에서 `run_next(block=True)` 반복
    - `snapshot() -> dict` — `{"staff": {role: {"name", "state", "say"}}, "jobs": [Job dict, 최신순 최대 20개]}` (복사본)
    - `load_history() -> None` — `jobs_dir/*/job.json` 최신 20개. 상태가 queued·running이면 `error`, 메시지 `"프로그램이 꺼져서 중단됐어."`
  - `merge(materials: list[Material], title: str) -> Material` — 본문은 `"\n\n---\n\n"`로 잇고, sources·warnings는 이어 붙이고, original은 처음 나온 것, 제목은 `title` 또는 첫 재료 제목

작업 처리 순서 (`_run_job`):
1. 모든 직원 `idle`, 실장 `working` "명령 읽는 중" → `plan = route(text, bool(files))` → `reply` 저장, 업무 일지에 실장 말.
2. `plan.error`면 `status = "needs_input"`, `reply = plan.error`. 단계가 없으면 바로 `done`.
3. 재료 단계: `scan` → `steps["scan"](files, say=…)`, `literature` → `steps["literature"](plan.work_query, say=…)`. `merge(재료들, plan.title)` → `title`, `warnings` 저장, `job_dir/source.txt` 저장 → `results["text"]`.
4. 결과 단계: `pdf` → `steps["pdf"](material, job_dir, say=…)` → `results["pdf"]`, `quiz` → `steps["quiz"](material, plan.question_count, job_dir, say=…)` → `results["quiz"]`. 주소는 `"/files/" + path.relative_to(root).as_posix()`.
5. 직원 상태: 일 시작 `working`, 끝 `done` + 한마디(예: 스캐너 "다 읽었어 (1,820자)"). 일지 줄 형식 `f"[{ROLES[role]}] {말}"`. 실장 마무리 "다 됐어! 결과 보관함 확인해".
6. `OfficeError` → `status = "error"`, `error = 메시지`, 그 직원 `error` + 같은 메시지. 그 밖 예외 → `traceback.print_exc()` 후 `error = "예상 못 한 오류가 났어. 로그: %LOCALAPPDATA%\ritual-office\office.log"`.
7. 끝나면 항상 `job_dir/job.json` 저장.

배포 처리 (`_run_deploy`): 배포담당 `working` "배포 준비 중" → `publish_quiz(job_dir, job.id, site_dir)` → `base = deploy(site_dir)` → `results["deploy_url"] = f"{base}/q/{job.id}/"`, 배포담당 `done` "배포 완료!". `OfficeError`면 `results["deploy_error"]`, 배포담당 `error` (작업 상태는 그대로 `done`). job.json 저장.

상태는 `threading.Lock` 하나로 보호한다 (`# ponytail: 전역 잠금 하나, 작업이 하나씩만 돌아서 충분`).

- [ ] **Step 1: `tests/conftest.py` 작성**

```python
import json
import pytest
from office import Material
from office.jobs import Office
from office.plan import Plan

def fake_route(text, has_files):
    if "운수" in text:
        return Plan(steps=["literature", "quiz"], title="운수 좋은 날", work_query="운수 좋은 날", question_count=5, reply="가져올게")
    if has_files:
        return Plan(steps=["scan", "pdf"], reply="PDF 만들게")
    return Plan(steps=["pdf"], error="자료가 없어. 프린트 사진을 첨부하거나 작품 이름을 알려줘.")

def fake_pdf(material, job_dir, say):
    path = job_dir / "note.pdf"
    path.write_bytes(b"%PDF-1.4")
    return path

def fake_quiz(material, count, job_dir, say):
    folder = job_dir / "quiz"
    folder.mkdir()
    (folder / "quiz.json").write_text(json.dumps({"title": material.title, "questions": []}, ensure_ascii=False), encoding="utf-8")
    (folder / "index.html").write_text("<h1>quiz</h1>", encoding="utf-8")
    return folder / "index.html"

@pytest.fixture
def make_office(tmp_path):
    def make(**steps):
        base = {"scan": lambda files, say: Material(title="세포", markdown="# 세포"),
                "literature": lambda query, say: Material(title=query, markdown="노트", original="원문"),
                "pdf": fake_pdf, "quiz": fake_quiz}
        base.update(steps)
        return Office(tmp_path, route=fake_route, steps=base, deploy=lambda site_dir: "https://ritual-quiz.vercel.app")
    return make
```

- [ ] **Step 2: 실패하는 테스트 작성** `tests/test_jobs.py`

```python
import pytest
from office import Material, OfficeError
from office.jobs import Office, merge

def test_scan_to_pdf_job_finishes(make_office):
    office = make_office()
    job_id, job_dir = office.new_job_dir()
    office.submit(job_id, "이 프린트 PDF로", [job_dir / "inputs" / "00.jpg"])
    assert office.run_next() is True
    snap = office.snapshot()
    job = snap["jobs"][0]
    assert job["status"] == "done" and job["title"] == "세포"
    assert job["results"]["pdf"] == f"/files/jobs/{job_id}/note.pdf"
    assert (job_dir / "source.txt").read_text(encoding="utf-8") == "# 세포"
    assert (job_dir / "job.json").exists()
    assert snap["staff"]["designer"]["state"] == "done" and snap["staff"]["manager"]["name"] == "실장"
    assert any(line.startswith("[스캐너]") for line in job["log"])

def test_missing_material_asks_back(make_office):
    office = make_office()
    job_id, _ = office.new_job_dir()
    office.submit(job_id, "PDF 만들어줘", [])
    office.run_next()
    job = office.snapshot()["jobs"][0]
    assert job["status"] == "needs_input" and job["reply"].startswith("자료가 없어")

def test_step_error_marks_job_and_worker_survives(make_office):
    def broken_scan(files, say):
        raise OfficeError("JPG·PNG·WEBP·PDF만 읽을 수 있어.")
    office = make_office(scan=broken_scan)
    j1, d1 = office.new_job_dir(); office.submit(j1, "PDF로", [d1 / "inputs" / "00.heic"])
    j2, _ = office.new_job_dir(); office.submit(j2, "운수 좋은 날 문제", [])
    office.run_next(); office.run_next()
    jobs = {j["id"]: j for j in office.snapshot()["jobs"]}
    assert jobs[j1]["status"] == "error" and "JPG" in jobs[j1]["error"]
    assert jobs[j2]["status"] == "done"

def test_unexpected_exception_is_caught(make_office):
    def crash(files, say):
        raise ValueError("boom")
    office = make_office(scan=crash)
    j, d = office.new_job_dir(); office.submit(j, "PDF로", [d / "inputs" / "00.jpg"]); office.run_next()
    assert office.snapshot()["jobs"][0]["error"].startswith("예상 못 한 오류")

def test_deploy_publishes_and_sets_url(make_office, tmp_path):
    office = make_office()
    j, _ = office.new_job_dir(); office.submit(j, "운수 좋은 날 문제", []); office.run_next()
    office.submit_deploy(j); office.run_next()
    assert office.snapshot()["jobs"][0]["results"]["deploy_url"] == f"https://ritual-quiz.vercel.app/q/{j}/"
    assert (tmp_path / "ritual-quiz" / "q" / j / "index.html").exists()

def test_deploy_requires_quiz(make_office):
    office = make_office()
    j, d = office.new_job_dir(); office.submit(j, "PDF로", [d / "inputs" / "00.jpg"]); office.run_next()
    with pytest.raises(OfficeError, match="문제 웹"):
        office.submit_deploy(j)

def test_history_survives_restart(make_office, tmp_path):
    office = make_office()
    j, d = office.new_job_dir(); office.submit(j, "PDF로", [d / "inputs" / "00.jpg"]); office.run_next()
    fresh = Office(tmp_path)
    fresh.load_history()
    assert fresh.snapshot()["jobs"][0]["id"] == j

def test_merge_two_sources():
    m = merge([Material(title="프린트", markdown="A", sources=["1.jpg"]),
               Material(title="운수 좋은 날", markdown="B", sources=["u"], original="원문")], title="")
    assert (m.title, m.markdown, m.sources, m.original) == ("프린트", "A\n\n---\n\nB", ["1.jpg", "u"], "원문")
```

- [ ] **Step 3: 실패 확인** — Expected: FAIL (`No module named 'office.jobs'`)
- [ ] **Step 4: `office/jobs.py` 구현**
- [ ] **Step 5: 통과 확인** — `tests/` 전체 실행. Expected: 전부 pass (Edge 없으면 PDF 테스트만 skip)
- [ ] **Step 6: 커밋** — `git add office/jobs.py tests/conftest.py tests/test_jobs.py` → `feat: add job queue and staff state`

---

### Task 9: 사무실 서버 (API)

**Files:**
- Create: `office/server.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `office.jobs.Office`, `office.llm.is_up`, `office.OfficeError`, `config.MODEL`, `config.WEB`
- Produces (Task 10 화면이 쓰는 계약):
  - `create_app(office: Office) -> FastAPI`, `app = create_app(Office())` (`uvicorn office.server:app`)
  - lifespan 시작 시 `office.load_history()`, `office.start()`
  - `POST /api/command` (multipart `text`, `files[]`) → `{"job_id": str}` / 글자도 파일도 없으면 400 `{"error": "명령을 입력해줘."}`
  - `GET /api/state` → `{**office.snapshot(), "ollama": bool, "model": str}`
  - `POST /api/jobs/{job_id}/deploy` → `{"ok": true}` / `OfficeError`면 400 `{"error": 메시지}`
  - `POST /api/jobs/{job_id}/open` → 그 작업 폴더를 `os.startfile` → `{"ok": true}` / 없는 작업 404
  - `POST /api/shutdown` → `{"ok": true}` 후 0.5초 뒤 `os._exit(0)` (`threading.Timer`)
  - `/files/...` → `office.root` 정적 파일, `/` → `WEB` 정적 파일(`html=True`). `/files`를 먼저 mount.

동작:
- 업로드는 `jobs_dir/<id>/inputs/{i:02d}{확장자}` 로 저장. 확장자는 원래 이름의 suffix를 소문자로, `^\.[a-z0-9]{1,5}$`에 안 맞으면 버린다. 원래 파일 이름은 경로에 쓰지 않는다 (경로 탈출 방지).
- 모듈 import 시 `mimetypes.add_type("text/javascript", ".js")`, `("text/css", ".css")`, `("font/woff2", ".woff2")` — Windows 레지스트리가 `.js`를 `text/plain`으로 잡아 모듈 스크립트가 막히는 경우가 있다.

- [ ] **Step 1: 실패하는 테스트 작성** `tests/test_server.py`

```python
from fastapi.testclient import TestClient
from office.server import create_app

def test_command_saves_upload_inside_job(make_office, tmp_path):
    client = TestClient(create_app(make_office()))
    r = client.post("/api/command", data={"text": "PDF로"}, files=[("files", ("../../evil.JPG", b"\xff\xd8", "image/jpeg"))])
    job_id = r.json()["job_id"]
    assert (tmp_path / "jobs" / job_id / "inputs" / "00.jpg").read_bytes() == b"\xff\xd8"
    assert not list(tmp_path.rglob("evil*"))

def test_empty_command_rejected(make_office):
    r = TestClient(create_app(make_office())).post("/api/command", data={"text": "  "})
    assert r.status_code == 400 and r.json()["error"] == "명령을 입력해줘."

def test_state_lists_staff_and_jobs(make_office):
    client = TestClient(create_app(make_office()))
    client.post("/api/command", data={"text": "운수 좋은 날 문제"})
    s = client.get("/api/state").json()
    assert set(s["staff"]) == {"manager", "scanner", "librarian", "designer", "examiner", "deployer"}
    assert s["jobs"][0]["status"] == "queued" and isinstance(s["ollama"], bool) and s["model"]

def test_deploy_unknown_job_is_400(make_office):
    r = TestClient(create_app(make_office())).post("/api/jobs/nope/deploy")
    assert r.status_code == 400 and r.json()["error"] == "그런 작업이 없어."

def test_output_files_are_served(make_office, tmp_path):
    client = TestClient(create_app(make_office()))
    (tmp_path / "jobs" / "x").mkdir(parents=True)
    (tmp_path / "jobs" / "x" / "note.pdf").write_bytes(b"%PDF")
    assert client.get("/files/jobs/x/note.pdf").content == b"%PDF"
```
(`TestClient`를 `with` 없이 쓰므로 lifespan·워커가 안 돈다 → 작업은 `queued`로 남는 게 정상)

- [ ] **Step 2: 실패 확인** — Expected: FAIL (`No module named 'office.server'`)
- [ ] **Step 3: `office/server.py` 구현**
- [ ] **Step 4: 통과 확인** — Expected: 5 passed
- [ ] **Step 5: 커밋** — `git add office/server.py tests/test_server.py` → `feat: add office api server`

---

### Task 10: 픽셀 아트 사무실 화면

**Files:**
- Create: `web/index.html`, `web/style.css`, `web/app.js`, `web/sprites.js`
- Test: `tests/test_server.py` (추가)

**Interfaces:**
- Consumes: Task 9의 API 계약, `web/fonts/*`, `web/logo-pixel.png`, `web/icon.ico`(Task 11에서 생김, 없어도 깨지지 않게)
- Produces: 화면 (다른 Task가 쓰는 코드 없음)

화면 규칙 (1440×900 기준, 창을 줄여도 가로 스크롤 없게):
- `<title>ritual의 공부 사무실</title>`, `<link rel="icon" href="icon.ico">`, `<script type="module" src="app.js">`.
- CSS 변수: `--c1`~`--c6` = PALETTE, `--bg #14111f`, `--panel #201a33`, `--line #3b2f5c`, `--ink #f3eefe`, `--muted #a99cc9`, `--ok #4ade80`, `--err #ff4d6d`. Galmuri11(일반·Bold) `@font-face`. 테두리 4px, 그림자 `4px 4px 0 #000`, `border-radius` 없음.
- 배치 (CSS grid): 위 64px 헤더 / 가운데 왼쪽 사무실 + 오른쪽 결과 보관함(380px) / 아래 업무 일지(140px) + 명령 바.
- 헤더: `logo-pixel.png`(높이 40px, pixelated) + "공부 사무실"(Galmuri Bold) + 상태등(`ollama` true → "AI 연결됨" 초록, false → "Ollama 꺼짐" 빨강) + 모델 이름 + [퇴근] (작업 중이면 한 번 더 눌러야 실행 → `POST /api/shutdown`).
- 사무실: 바닥 타일 패턴, 책상 6개(3×2), 순서 실장·스캐너·사서 / 디자이너·출제위원·배포담당. 책상마다 캐릭터 캔버스(16×16 → 4배 = 64px), 이름표(한국어 이름), 상태등(idle 회색 / working `--c3` 깜빡임 / done 초록 / error 빨강), 말풍선(`say`, 두 줄 넘으면 말줄임).
- `sprites.js`: `export const SPRITES = { manager: { colors: {문자: "#hex"}, frames: [[16줄×16글자], [16줄×16글자]] }, ... }` — `.`은 투명. 직원마다 구분되는 머리·옷 색과 소품(실장 넥타이, 스캐너 안경, 사서 책, 디자이너 베레모, 출제위원 연필, 배포담당 모자). `working`이면 두 프레임을 300ms마다 바꿔 타자 치는 모습, `idle`이면 1초마다 1px 위아래.
- 명령 바: textarea (Enter 보내기, Shift+Enter 줄바꿈), 첨부 버튼(`accept=".jpg,.jpeg,.png,.webp,.pdf"`, 여러 개), 창 전체에 끌어다 놓기, 첨부 파일 칩(✕로 빼기), [보내기]. 보낼 땐 `FormData`로 `POST /api/command`, 400이면 `error`를 명령 바 위에 빨간 글씨로. placeholder: `예) 이 프린트 예쁘게 PDF로 만들어줘 / 운수 좋은 날 가져와서 문제 10개 만들어줘`.
- 결과 보관함: 작업 카드 최신순. 제목(없으면 명령 앞 30자), 상태 배지(대기·진행 중·완료·에러·되물음), 실장 말(`reply`), 경고(`warnings`), 에러. 버튼은 결과가 있을 때만: [PDF 열기](`results.pdf`, 새 창) · [문제 미리보기](`results.quiz`) · [텍스트](`results.text`) · [폴더](`POST /open`) · [배포]. [배포]는 첫 클릭에 "공개 링크로 올릴까? 한 번 더 누르면 배포"로 바뀌고 두 번째 클릭에 `POST /deploy`. `deploy_url`이 있으면 링크 + [복사](`navigator.clipboard`), `deploy_error`면 빨간 글씨.
- 업무 일지: 최신 작업의 `log`, 직원 이름은 그 직원 색으로.
- 폴링: `GET /api/state` 1000ms마다. 실패하면 "사무실 서버가 꺼졌어" 덮개 화면.
- 브라우저 대화상자(`alert`, `confirm`) 금지 — 두 번 누르기와 화면 안 메시지로 대신한다.

- [ ] **Step 1: 실패하는 테스트 추가** `tests/test_server.py`

```python
def test_index_served(make_office):
    r = TestClient(create_app(make_office())).get("/")
    assert r.status_code == 200 and "공부 사무실" in r.text and 'src="app.js"' in r.text
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL (404)
- [ ] **Step 3: `web/` 네 파일 구현**
- [ ] **Step 4: 통과 확인** — Expected: 6 passed
- [ ] **Step 5: 눈으로 확인**
  1. 서버를 백그라운드로: `$env:UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\ritual-office\venv"; uv run uvicorn office.server:app --host 127.0.0.1 --port 8765`
  2. `& 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' --headless --disable-gpu --window-size=1440,900 "--user-data-dir=$env:LOCALAPPDATA\ritual-office\edge-headless" "--screenshot=$env:TEMP\office.png" http://127.0.0.1:8765/` → Read로 확인: 로고, 책상 6개와 캐릭터, Galmuri 한글, 넘치는 곳 없음.
  3. 한글 명령은 Python으로 보낸다 (`curl.exe`는 인자를 CP949로 넘겨 한글이 깨짐): `$env:UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\ritual-office\venv"; uv run python -c "import httpx; print(httpx.post('http://127.0.0.1:8765/api/command', data={'text': '안녕'}).json())"` → 2초 뒤 다시 찍어서 실장 말풍선·결과 카드가 보이는지 확인.
  4. 서버 종료 (`curl.exe -X POST http://127.0.0.1:8765/api/shutdown`).
- [ ] **Step 6: 커밋** — `git add web/index.html web/style.css web/app.js web/sprites.js tests/test_server.py` → `feat: add pixel art office ui`

---

### Task 11: 바탕화면 아이콘 실행

**Files:**
- Create: `launch.pyw`, `install.ps1`
- Modify: `office/assets.py` (`build_icon`, `__main__`)
- Test: `tests/test_assets.py` (추가)

**Interfaces:**
- Consumes: `office.server.app`, `config.HOST`, `config.PORT`, `config.OLLAMA_URL`, `config.BROWSERS`, `config.DATA`, `config.LOGO`, `config.WEB`
- Produces:
  - `office.assets.build_icon(src: Path, out: Path) -> None`
  - `python -m office.assets` → `web/logo-pixel.png`, `web/icon.ico` 생성
  - `launch.pyw`: `is_up(url: str) -> bool`, `ensure_ollama() -> None`, `open_window() -> None`, `main() -> None`
  - 바탕화면 바로가기 `ritual의 공부 사무실.lnk`

동작:
- `build_icon`: 로고에서 `src.crop((0, 0, 305, 높이))`의 알파 bbox = 글자 "r" → 정사각형으로 여백 → 24×24 LANCZOS, 알파 0/255 → 32×32 타일(바탕 `#14111f`, 1px 테두리 `#9337FD`) 가운데에 붙임 → 크기 16·24·32·48·64·128·256을 각각 NEAREST로 만들어 ICO 한 파일(`append_images`)로 저장.
- `launch.pyw` (pythonw 실행, 콘솔 없음):
  - 맨 위에서 `DATA` 폴더를 만들고 `sys.stdout = sys.stderr = open(DATA / "office.log", "a", encoding="utf-8", buffering=1)` — pythonw는 stdout이 `None`이라 uvicorn 로그가 터진다.
  - `is_up`: `urllib.request.urlopen(url, timeout=1)` 성공 여부.
  - `main`: `/api/state`가 이미 응답하면 `open_window()`만 하고 끝 (두 번 눌러도 서버 하나). 아니면 `ensure_ollama()` → 서버가 뜰 때까지(최대 30초) 기다렸다 창을 여는 스레드 시작 → `uvicorn.run("office.server:app", host=HOST, port=PORT)`.
  - `ensure_ollama`: `/api/version`이 응답 없으면 `subprocess.Popen(["ollama", "serve"], creationflags=subprocess.CREATE_NO_WINDOW)` 후 최대 20초 대기. `ollama`가 없으면 로그만 남긴다 (화면 상태등이 알려줌).
  - `open_window`: `BROWSERS` 첫 번째로 `[browser, f"--app=http://{HOST}:{PORT}/", "--window-size=1440,900"]`. 없으면 `webbrowser.open`.
- `install.ps1` (UTF-8 BOM, `$ErrorActionPreference = 'Stop'`, `$root = $PSScriptRoot`, `$env:UV_PROJECT_ENVIRONMENT = "$env:LOCALAPPDATA\ritual-office\venv"`):
  1. `uv`, `ollama`, `npm` 없으면 `throw "<이름>이(가) 없어. 먼저 설치해줘."`
  2. `ollama list`에 `qwen3.5`가 없으면 `ollama pull qwen3.5`
  3. `$root`에서 `uv sync` → `uv run python -m office.assets` (각각 `$LASTEXITCODE` 확인)
  4. `vercel` 없으면 `npm i -g vercel`
  5. 바로가기: `Join-Path ([Environment]::GetFolderPath('Desktop')) 'ritual의 공부 사무실.lnk'`, `WScript.Shell`의 `CreateShortcut` — TargetPath `$env:UV_PROJECT_ENVIRONMENT\Scripts\pythonw.exe`, Arguments `"$root\launch.pyw"`(따옴표 포함), WorkingDirectory `$root`, IconLocation `$root\web\icon.ico`, Description `ritual의 공부 사무실`
  6. 끝 안내: `설치 완료. 배포 기능을 쓰려면 터미널에서 vercel login 을 한 번 해줘.`

- [ ] **Step 1: 실패하는 테스트 추가** `tests/test_assets.py`

```python
from office.assets import build_icon

def test_icon_has_all_sizes(tmp_path):
    out = tmp_path / "icon.ico"
    build_icon(LOGO, out)
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= Image.open(out).info["sizes"]
```

- [ ] **Step 2: 실패 확인** — Expected: FAIL (`cannot import name 'build_icon'`)
- [ ] **Step 3: `build_icon`, `office/assets.py`의 `__main__`, `launch.pyw`, `install.ps1` 구현** → `install.ps1`을 BOM으로 다시 저장:
```powershell
$p = Resolve-Path install.ps1; [IO.File]::WriteAllText($p, [IO.File]::ReadAllText($p), (New-Object Text.UTF8Encoding $true))
```
- [ ] **Step 4: 통과 확인** — `tests/test_assets.py`. Expected: 2 passed
- [ ] **Step 5: 설치·실행 확인** (사용자 PC 변경: 전역 `npm i -g vercel`, 바탕화면 바로가기 생성)
  1. `powershell -ExecutionPolicy Bypass -File install.ps1` → 종료 코드 0, 바탕화면에 `ritual의 공부 사무실.lnk`.
  2. 아이콘 미리보기: `web/icon.ico`를 Pillow로 PNG 저장해 Read로 본다 (픽셀 r, 어두운 타일).
  3. `Start-Process (Join-Path ([Environment]::GetFolderPath('Desktop')) 'ritual의 공부 사무실.lnk')` → 30초 안에 `http://127.0.0.1:8765/api/state` 200, Edge 앱 창이 뜸.
  4. 한 번 더 실행 → `(Get-NetTCPConnection -LocalPort 8765 -State Listen).Count` 가 1.
  5. `curl.exe -X POST http://127.0.0.1:8765/api/shutdown` → 포트가 닫힘. `%LOCALAPPDATA%\ritual-office\office.log`에 에러 없음.
- [ ] **Step 6: 커밋** — `git add launch.pyw install.ps1 office/assets.py tests/test_assets.py` → `feat: launch from desktop icon`

---

### Task 12: 내 PC 실측 + README

**Files:**
- Create: `tests/fixtures/handout.html`, `tests/test_live.py`, `README.md`
- Modify: `office/config.py` (실측 결과에 따라 `NUM_CTX`, `MAX_IMAGE_SIDE`만)

**Interfaces:**
- Consumes: `scan`, `make_pdf`, `make_quiz_page`, `fetch_literature`, `config.BROWSERS`, `config.DATA`
- Produces: 실측 숫자 (README), 최종 설정값

- [ ] **Step 1: 시험용 프린트 작성** `tests/fixtures/handout.html` — A4 한 장짜리 "세포의 구조" 정리 프린트 (제목, 섹션 4개: 핵 / 미토콘드리아 / 세포막 / 엽록체와 세포벽, 작은 표 1개, 약 800자, 맑은 고딕). 낱말 "미토콘드리아", "세포막", "엽록체"가 꼭 들어간다.

- [ ] **Step 2: 실측 테스트 작성** `tests/test_live.py`

```python
import json, os, subprocess, time
from pathlib import Path
import pytest
from office.config import BROWSERS, DATA
from office.literature import fetch_literature
from office.note import make_pdf
from office.quiz import make_quiz_page
from office.scan import scan

pytestmark = pytest.mark.skipif(os.environ.get("RITUAL_LIVE") != "1", reason="실제 Ollama 실측은 RITUAL_LIVE=1일 때만")
HANDOUT = Path(__file__).parent / "fixtures" / "handout.html"

def test_handout_to_pdf_and_quiz(tmp_path):
    shot = tmp_path / "handout.png"
    browser = next(p for p in BROWSERS if p.exists())
    subprocess.run([str(browser), "--headless", "--disable-gpu", "--window-size=1240,1754",
                    f"--user-data-dir={DATA / 'edge-headless'}", f"--screenshot={shot}", HANDOUT.as_uri()], timeout=60)
    t0 = time.perf_counter(); m = scan([shot]); t1 = time.perf_counter()
    assert "미토콘드리아" in m.markdown and "세포막" in m.markdown
    pdf = make_pdf(m, tmp_path); t2 = time.perf_counter()
    make_quiz_page(m, 5, tmp_path); t3 = time.perf_counter()
    quiz = json.loads((tmp_path / "quiz" / "quiz.json").read_text(encoding="utf-8"))
    assert pdf.exists() and len(quiz["questions"]) >= 3
    print(f"\n[실측] OCR {t1 - t0:.0f}초 / PDF {t2 - t1:.0f}초 / 문제 5개 {t3 - t2:.0f}초")

def test_literature_public_domain():
    t0 = time.perf_counter()
    m = fetch_literature("운수 좋은 날")
    assert m.original and m.original.startswith("새침하게") and m.markdown
    print(f"\n[실측] 작품 가져오기 {time.perf_counter() - t0:.0f}초")
```

- [ ] **Step 3: 실측 실행** (전원 연결 상태)
```powershell
$env:RITUAL_LIVE="1"; $env:UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\ritual-office\venv"; uv run pytest tests/test_live.py -v -s
```
돌아가는 동안 `nvidia-smi --query-gpu=memory.used,memory.total --format=csv` 로 VRAM 기록. Expected: 2 passed + `[실측]` 줄.
OCR이 한 장에 180초를 넘거나 메모리 부족 에러가 나면 `NUM_CTX = 8192`, `MAX_IMAGE_SIDE = 1280`으로 바꿔 다시 재고, 두 결과를 다 적는다.

- [ ] **Step 4: 화면 끝까지 확인** — 바탕화면 아이콘으로 실행 → Step 3에서 만든 프린트 PNG를 Python으로 보낸다: `uv run python -c "import httpx; print(httpx.post('http://127.0.0.1:8765/api/command', data={'text': '이 프린트 PDF로 만들고 문제 5개도 만들어줘'}, files=[('files', open(r'<handout.png 경로>', 'rb'))]).json())"` (앞에 venv 접두어) → `/api/state`에서 `done`이 될 때까지 확인 → 화면을 다시 찍어 직원 상태·결과 카드 확인 → PDF와 문제 미리보기 주소가 200인지 확인.

- [ ] **Step 5: 실제 배포 1회 — 사용자에게 먼저 묻고 승인받은 뒤에만** (공개 링크가 생김)
  사용자가 `vercel login`을 마친 상태에서 화면의 [배포]를 두 번 누르거나 `curl.exe -X POST http://127.0.0.1:8765/api/jobs/<id>/deploy`. 받은 `deploy_url`을 `Invoke-WebRequest`로 열어 200이고 문제 제목이 보이는지 확인 (로그인 벽이면 401이나 vercel.com 로그인 페이지로 감).

- [ ] **Step 6: `README.md` 작성** — 무엇인지(한 줄), 설치(`powershell -ExecutionPolicy Bypass -File install.ps1`, `vercel login`), 쓰는 법(명령 예시 3개), 직원 소개, **내 PC 실측** 표(OCR·PDF·문제·작품 가져오기 초, VRAM 사용량, 쓴 `NUM_CTX`), 고급 모드(`setx RITUAL_MODEL qwen3.6:latest` 후 재실행, 느리고 RAM 23GB 사용), 결과물 위치(`output/`), 배포한 문제 내리기(`output/ritual-quiz/q/<id>` 삭제 후 아무 문제나 [배포]), 문제 해결(Ollama 꺼짐, 느릴 때 GPU 쓰는 앱 끄기·전원 연결, 로그 `%LOCALAPPDATA%\ritual-office\office.log`), 폰트 라이선스(Galmuri, OFL).

- [ ] **Step 7: 전체 테스트 + 커밋**
Run: `$env:UV_PROJECT_ENVIRONMENT="$env:LOCALAPPDATA\ritual-office\venv"; uv run pytest -v` → 전부 pass (live는 skip)
`git add tests/fixtures/handout.html tests/test_live.py README.md office/config.py` → `docs: add readme with measured speeds`
