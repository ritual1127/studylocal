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


def test_phase2_office_live(tmp_path):
    """실제 qwen3.5로 실장 라우팅 + 새 직원 전부 + 반려 후 다시 만들기. 알림은 가짜(내 PC·폰으로 안 감)."""
    import datetime
    import shutil
    import zipfile
    from office.jobs import Office
    from office.planner import Planner

    class Quiet:
        settings = {"job_done": True}
        sent = []

        def send(self, title, body, reminder=False):
            self.sent.append(title)
            return []

    from office.plan import route
    # 실장 라우터 + 직원 파이프라인 실측 (실장님 에이전트는 test_rab_agent_live)
    office = Office(tmp_path / "out", route=route, planner=Planner(tmp_path / "planner.json"), notifier=Quiet())
    shot = tmp_path / "handout.png"
    browser = next(p for p in BROWSERS if p.exists())
    subprocess.run([str(browser), "--headless", "--disable-gpu", "--window-size=1240,1754",
                    f"--user-data-dir={DATA / 'edge-headless'}", f"--screenshot={shot}", HANDOUT.as_uri()], timeout=60)
    docx = tmp_path / "세포.docx"
    with zipfile.ZipFile(docx, "w") as z:
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
                   '<w:p><w:r><w:t>세포는 생물을 이루는 기본 단위이다.</w:t></w:r></w:p>'
                   '<w:p><w:r><w:t>핵에는 유전 물질인 DNA가 들어 있다.</w:t></w:r></w:p></w:body></w:document>')
    cases = [
        ("광합성이 뭐야? 쉽게 설명해줘", [], {"answer"}),
        ("광합성 조사해서 암기카드 10장이랑 마인드맵 만들어줘", [], {"research", "cards", "mindmap"}),
        ("이거 분석해줘", [shot], {"scan", "analysis"}),
        ("이 문서 영어로 번역해줘", [docx], {"scan", "translate"}),
        ("내일 오후 3시 수학 학원 일정 넣어주고 할 일에 영어 단어 30개 넣어줘", [], {"schedule"}),
        ("기말고사가 11월 20일인데 공부 계획 짜줘", [], {"plan"}),
        ("25분 공부모드 켜줘", [], {"focus"}),
        ("운수 좋은 날 가져와서 문제 5개 만들어줘", [], {"literature", "quiz"}),
        ("방금 자료로 암기카드 만들어줘", [], {"cards"}),
    ]
    jobs = {}
    for text, files, expected in cases:
        job_id, job_dir = office.new_job_dir()
        inputs = [shutil.copy(f, job_dir / "inputs" / f"00{f.suffix}") for f in files]
        office.submit(job_id, text, [Path(p) for p in inputs])
        t0 = time.perf_counter()
        office.run_next()
        job = jobs[text] = office.jobs[job_id]
        print(f"\n[실측] {text} → {job.steps} {job.status} {time.perf_counter() - t0:.0f}초 · {job.title}")
        assert expected <= set(job.steps), (job.steps, job.reply, job.error)
        assert job.status in ("review", "done"), (job.status, job.error, job.reply)
        for url in job.results.values():
            if url.startswith("/files/"):
                assert (office.root / url.removeprefix("/files/")).stat().st_size > 0

    view = office.planner.view()
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    assert any(e["date"] == tomorrow and e["time"] == "15:00" and "학원" in e["title"] for e in view["events"])
    assert any("단어" in t["text"] for t in view["all_todos"]) and len(view["all_todos"]) >= 3
    assert view["focus"] and view["focus"]["minutes"] == 25
    cards = jobs["광합성 조사해서 암기카드 10장이랑 마인드맵 만들어줘"]
    office.reject(cards.id, "카드 뒷면을 더 짧고 쉽게")
    t0 = time.perf_counter()
    office.run_next()
    assert cards.status == "review" and cards.revision == 1 and cards.error is None
    print(f"\n[실측] 반려 → 다시 만들기 {time.perf_counter() - t0:.0f}초, 알림 {len(Quiet.sent)}개")


def test_rab_agent_live(tmp_path):
    """실제 qwen3.5로 실장님: 파일 찾아 가져오기 · 폰 메시지 · 오늘 현황 · 팀 지정. 알림은 가짜, 폴더는 임시."""
    from office.jobs import Office
    from office.planner import Planner
    from office.tools import Files

    class Quiet:
        settings = {"job_done": True, "phone": True, "pc": True}

        def __init__(self):
            self.to = []

        def send(self, title, body, reminder=False, only=None):
            self.to.append((only or "both", body))
            return []

    home = tmp_path / "home"
    for name in ("Desktop", "Documents", "Downloads"):
        (home / name).mkdir(parents=True)
    shutil_src = HANDOUT
    (home / "Desktop" / "세포_정리_프린트.html").write_text(shutil_src.read_text(encoding="utf-8"), encoding="utf-8")
    files = Files(roots=[home], folders={n: home / n for n in ("Desktop", "Documents", "Downloads")}, perms={"read": True, "write": True})
    notifier = Quiet()
    office = Office(tmp_path / "out", planner=Planner(tmp_path / "planner.json"), notifier=notifier, files=files, opener=lambda t: None)
    office.planner.add_todo("영어 단어 30개", time="21:00")

    def ask(text):
        job_id, _ = office.new_job_dir()
        office.submit(job_id, text, [])
        t0 = time.perf_counter()
        office.run_next()
        job = office.jobs[job_id]
        print(f"\n[실장님 실측] {text} → {job.status} {time.perf_counter() - t0:.0f}초 · 도구 {job.trace} · 답: {job.reply[:80]}")
        return job

    brought = ask("바탕화면에서 세포 정리 프린트 찾아서 가져와")
    assert brought.names and brought.names[0].startswith("세포_정리_프린트")
    ask("내 폰으로 굿나잇이라고 보내")
    assert any(to == "phone" and "굿나잇" in body for to, body in notifier.to)
    today = ask("오늘 할 일 뭐야?")
    assert "영어 단어" in today.reply
    quiz = ask("@출제위원 바탕화면 세포 정리 프린트로 문제 5개 만들어줘")
    assert quiz.assignee == "examiner" and "quiz" in quiz.results and quiz.status == "review"
