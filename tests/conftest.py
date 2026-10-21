import json
import pytest
from office import Material
from office.jobs import Office
from office.plan import Plan
from office.planner import Planner

def fake_route(text, has_files, has_ref=False):
    if "운수" in text:
        return Plan(steps=["literature", "quiz"], title="운수 좋은 날", work_query="운수 좋은 날", question_count=5, reply="가져올게")
    if has_files:
        return Plan(steps=["scan", "pdf"], reply="PDF 만들게")
    return Plan(steps=["pdf"], error="자료가 없어. 프린트 사진을 첨부하거나 작품 이름을 알려줘.")

def page(job_dir, folder, *extra):
    (job_dir / folder).mkdir(exist_ok=True)
    for name in extra:
        (job_dir / folder / name).write_text("x", encoding="utf-8")
    (job_dir / folder / "index.html").write_text(f"<h1>{folder}</h1>", encoding="utf-8")
    return job_dir / folder / "index.html"

def fake_pdf(material, job_dir, say, feedback=""):
    path = job_dir / "note.pdf"
    path.write_bytes(b"%PDF-1.4")
    return path

def fake_quiz(material, count, job_dir, say, feedback=""):
    path = page(job_dir, "quiz")
    (job_dir / "quiz" / "quiz.json").write_text(json.dumps({"title": material.title, "questions": []}, ensure_ascii=False), encoding="utf-8")
    return path

def fake_answer(question, material, job_dir, say, feedback=""):
    path = job_dir / "answer.md"
    path.write_text(f"답: {question}", encoding="utf-8")
    return path

class FakeNotifier:
    def __init__(self):
        self.settings = {"job_done": True}
        self.sent = []

        self.settings.update({"pc": True, "phone": True, "ai": "fast", "briefing": "07:30"})
        self.to = []

    def send(self, title, body, reminder=False, only=None):
        self.sent.append(title)
        self.to.append((only or "both", title, body))
        return [] if only != "phone" or self.settings["phone"] else ["폰: 폰 알림이 꺼져 있어. 설정에서 켜줘."]

    def update(self, changes):
        self.settings.update(changes)
        return dict(self.settings)

def fake_steps():
    return {"scan": lambda files, say: Material(title="세포", markdown="# 세포"),
                "literature": lambda query, say: Material(title=query, markdown="노트", original="원문"),
                "research": lambda topic, say: Material(title=topic, markdown=f"# {topic}", sources=["wiki"]),
                "pdf": fake_pdf, "quiz": fake_quiz, "answer": fake_answer,
                "cards": lambda material, count, job_dir, say, feedback="": page(job_dir, "cards", "cards.csv"),
                "mindmap": lambda material, job_dir, say, feedback="": page(job_dir, "mindmap"),
                "analysis": lambda material, job_dir, say, feedback="": page(job_dir, "analysis"),
                "translate": lambda material, target, job_dir, say, feedback="": page(job_dir, "translation", "translation.md"),
                "schedule": lambda text, today: {"events": [], "todos": [{"text": text, "date": today.isoformat(), "time": ""}],
                                                 "reply": "넣었어"},
                "plan": lambda text, today, exams, material: {"todos": [{"date": today.isoformat(), "text": "1단원"}],
                                                              "reply": "짰어"}}

@pytest.fixture
def make_office(tmp_path):
    def make(route=fake_route, **steps):
        base = fake_steps()
        base.update(steps)
        return Office(tmp_path, route=route, steps=base, deploy=lambda site_dir: "https://ritual-quiz.vercel.app",
                      planner=Planner(tmp_path / "planner.json"), notifier=FakeNotifier())
    return make


@pytest.fixture
def agent_home(tmp_path):
    home = tmp_path / "home"
    for name in ("Desktop", "Documents", "Downloads"):
        (home / name).mkdir(parents=True)
    (home / "Desktop" / "수학_프린트.pdf").write_bytes(b"%PDF-1.4")
    (home / "Downloads" / "수학 숙제.hwp").write_bytes(b"x")
    return home

@pytest.fixture
def make_agent_office(tmp_path, agent_home):
    from office.tools import Files

    def make(script, **steps):
        base = fake_steps()
        base.update(steps)
        opened = []
        files = Files(roots=[agent_home], folders={n: agent_home / n for n in ("Desktop", "Documents", "Downloads")},
                      perms={"read": True, "write": True})
        office = Office(tmp_path / "out", steps=base, deploy=lambda site_dir: "https://ritual-quiz.vercel.app",
                        planner=Planner(tmp_path / "planner.json"), notifier=FakeNotifier(), agent_llm=script,
                        files=files, opener=opened.append)
        office.opened = opened
        return office
    return make
