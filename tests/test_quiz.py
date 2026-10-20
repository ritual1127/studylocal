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
