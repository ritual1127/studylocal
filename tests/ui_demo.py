"""화면 확인용 가짜 사무실: AI 없이 바로 끝나는 직원들 + 미리 채운 작업·일정. E2E 테스트와 스크린샷에 쓴다."""
import datetime
import json
import threading
import time
import urllib.request
from pathlib import Path

from office import Material, OfficeError, llm, server
from office.jobs import Office
from office.plan import Plan
from office.planner import Planner

ROUTES = {
    "운수 좋은 날 문제": Plan(steps=["literature", "quiz"], title="운수 좋은 날", work_query="운수 좋은 날", question_count=5,
                       reply="사서한테 원문 가져오라고 할게"),
    "광합성이 뭐야?": Plan(steps=["answer"], question="광합성이 뭐야?", title="광합성 질문", reply="선생님이 답해줄게"),
    "광합성 조사해서 암기카드랑 마인드맵": Plan(steps=["research", "cards", "mindmap"], topic="광합성", title="광합성",
                                    reply="조사원이 찾고 암기담당·정리왕이 만들게"),
    "25분 공부모드": Plan(steps=["focus"], focus_minutes=25, reply="코치가 타이머 켤게"),
    "안녕": Plan(steps=[], reply="안녕! 오늘은 뭐 공부해?"),
}


def route(text, has_files, has_ref=False):
    if has_files:
        return Plan(steps=["scan", "analysis", "pdf"], reply="스캐너가 읽고 분석·노트까지 할게")
    if has_ref:
        return Plan(steps=["quiz"], question_count=5, reply="고른 자료로 문제 낼게")
    return ROUTES.get(text) or Plan(steps=["pdf"], error="자료가 없어. 프린트 사진을 첨부하거나 작품 이름을 알려줘.")


def page(job_dir, folder, title, *extra):
    (job_dir / folder).mkdir(exist_ok=True)
    for name in extra:
        (job_dir / folder / name).write_text("앞,뒤\n", encoding="utf-8")
    (job_dir / folder / "index.html").write_text(f"<!doctype html><meta charset=utf-8><h1>{title}</h1>", encoding="utf-8")
    return job_dir / folder / "index.html"


def scan(files, say):
    if any(Path(f).suffix == ".bin" for f in files):
        raise OfficeError("이 파일은 못 읽어. 사진·PDF·한글·워드·파워포인트·엑셀·글자 파일만 돼.")
    time.sleep(0.3)
    return Material(title="세포의 구조", markdown="# 세포의 구조\n핵은 유전 물질을 담는다.", sources=[Path(f).name for f in files])


def pdf(material, job_dir, say, feedback=""):
    (job_dir / "note.pdf").write_bytes(b"%PDF-1.4\n%demo\n")
    return job_dir / "note.pdf"


STEPS = {
    "scan": scan,
    "literature": lambda q, say: Material(title=q, markdown="# 운수 좋은 날\n김첨지 이야기", original="새침하게 흐린 품이…"),
    "research": lambda t, say: Material(title=t, markdown=f"# {t}\n빛에너지로 양분을 만든다.", sources=["위키백과"]),
    "analysis": lambda m, d, say, feedback="": page(d, "analysis", "분석 보고서"),
    "pdf": pdf,
    "quiz": lambda m, n, d, say, feedback="": page(d, "quiz", "문제"),
    "cards": lambda m, n, d, say, feedback="": page(d, "cards", "암기카드", "cards.csv"),
    "mindmap": lambda m, d, say, feedback="": page(d, "mindmap", "마인드맵"),
    "translate": lambda m, t, d, say, feedback="": page(d, "translation", "번역"),
    "answer": lambda q, m, d, say, feedback="": _answer(d),
    "schedule": lambda text, today: {"events": [], "todos": [{"text": text, "date": today.isoformat(), "time": ""}], "reply": "넣었어"},
    "plan": lambda text, today, exams, m: {"todos": [{"date": today.isoformat(), "text": "1단원 복습"}], "reply": "화이팅"},
}


def _answer(job_dir):
    path = job_dir / "answer.md"
    path.write_text("광합성은 식물이 **빛에너지**로 물과 이산화 탄소에서 양분(포도당)을 만드는 과정이야.\n산소가 함께 나와.",
                    encoding="utf-8")
    return path


class Notifier:
    def __init__(self):
        self.settings = {"pc": True, "phone": False, "topic": "", "server": "https://ntfy.sh", "job_done": True,
                         "briefing": "07:30", "ai": "fast"}
        self.history = []
        self.sent = []

    def send(self, title, body, reminder=False):
        self.sent.append(title)
        self.history.insert(0, {"time": f"{datetime.datetime.now():%m-%d %H:%M}", "title": title, "body": body, "errors": []})
        return []

    def update(self, changes):
        self.settings.update({k: v for k, v in changes.items() if k in self.settings})
        if changes.get("phone") and not self.settings["topic"]:
            self.settings["topic"] = "ritual-demo-topic"
        return dict(self.settings)


def make_demo_office(root: Path, seed: bool = True) -> Office:
    office = Office(root, route=route, steps=STEPS, deploy=lambda site: "https://ritual-quiz.vercel.app",
                    planner=Planner(root / "planner.json"), notifier=Notifier())
    if not seed:
        return office

    def run(text, files=()):
        job_id, job_dir = office.new_job_dir()
        paths = []
        for name in files:
            (job_dir / "inputs" / name).write_bytes(b"x")
            paths.append(job_dir / "inputs" / name)
        office.submit(job_id, text, paths, names=list(files))
        office.run_next()
        time.sleep(1.05)  # 작업 번호(초 단위)가 겹치지 않게
        return office.jobs[job_id]

    approved = run("운수 좋은 날 문제")
    office.approve(approved.id, "좋아, 배포해도 돼")
    run("광합성이 뭐야?")
    run("광합성 조사해서 암기카드랑 마인드맵")
    reworked = run("이 프린트 정리해줘", ["세포 프린트.jpg"])
    office.reject(reworked.id, "표를 더 넣어줘")
    office.run_next()
    run("PDF 만들어줘")
    run("이거 읽어줘", ["이상한.bin"])
    run("기말 대비 프린트", ["기말 대비.hwp"])

    p = office.planner
    today = p.now().date()
    p.add_todo("영어 단어 30개", time="21:00")
    done = p.add_todo("수학 문제집 3쪽")
    p.update_todo(done["id"], {"done": True})
    p.add_todo("과학 실험 보고서", date=(today - datetime.timedelta(days=1)).isoformat())
    p.add_event("기말고사", (today + datetime.timedelta(days=10)).isoformat(), kind="시험")
    p.add_event("수학 학원", today.isoformat(), time="18:00", remind=10, repeat="weekly")
    p.add_event("독서 감상문 마감", (today + datetime.timedelta(days=3)).isoformat(), kind="숙제")
    p.add_event("수행평가", (today + datetime.timedelta(days=45)).isoformat(), kind="시험")
    p.data["focus"]["log"] += [{"date": (today - datetime.timedelta(days=d)).isoformat(), "minutes": m, "task": ""}
                               for d, m in ((1, 50), (2, 25), (3, 75))] + [{"date": today.isoformat(), "minutes": 40, "task": ""}]
    p._save()
    return office


PHONE_PORT = 8798


def serve(office: Office, port: int) -> threading.Thread:
    """가짜 사무실을 port에서 띄운다 (모델 올리기는 건너뜀)."""
    import uvicorn

    from office.remote import Remote, start_uvicorn

    server.LOCAL.update({f"127.0.0.1:{port}", f"localhost:{port}"})
    llm.warm = lambda: None
    # 폰 서버는 이 PC 안(127.0.0.1)에서만, 진짜 사무실(8766)과 다른 포트로: 방화벽 창·인터넷 노출·포트 충돌 없게
    remote = Remote(office.root / "remote.json", port=PHONE_PORT,
                    start_server=lambda host: start_uvicorn(lambda: server.create_remote_app(office, remote), "127.0.0.1", PHONE_PORT),
                    start_tunnel=lambda on_url: (on_url("https://demo-tunnel.trycloudflare.com"), lambda: None)[1],
                    notify=lambda title, body: office.notifier.send(title, body), lan=lambda: ["127.0.0.1"])
    app = server.create_app(office, remote=remote)
    thread = threading.Thread(target=uvicorn.run, args=(app,), kwargs={"host": "127.0.0.1", "port": port, "log_level": "warning"},
                              daemon=True)
    thread.start()
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1):
                return thread
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("가짜 사무실이 안 켜졌어")


if __name__ == "__main__":
    import sys
    import tempfile

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    root = Path(tempfile.mkdtemp(prefix="ritual-demo-"))
    serve(make_demo_office(root), port)
    print(json.dumps({"port": port, "root": str(root)}), flush=True)
    threading.Event().wait()
