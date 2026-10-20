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
