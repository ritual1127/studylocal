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

    def send(self, title, body, reminder=False):
        self.sent.append(title)
        return []

@pytest.fixture
def make_office(tmp_path):
    def make(route=fake_route, **steps):
        base = {"scan": lambda files, say: Material(title="세포", markdown="# 세포"),
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
        base.update(steps)
        return Office(tmp_path, route=route, steps=base, deploy=lambda site_dir: "https://ritual-quiz.vercel.app",
                      planner=Planner(tmp_path / "planner.json"), notifier=FakeNotifier())
    return make
