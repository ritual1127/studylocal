import csv
import datetime
import json
import pytest
from office import Material, OfficeError
from office.cards import make_cards_page, validate_cards
from office.coach import make_study_plan
from office.mindmap import make_mindmap_page, validate_mindmap
from office.research import research
from office.secretary import parse_schedule
from office.tutor import answer_question

TODAY = datetime.date(2026, 10, 21)
CELL = Material(title="세포의 구조", markdown="# 세포의 구조\n미토콘드리아는 세포 호흡을 한다.")


# ---- 조사원 ----
def wiki(hits, extract):
    def get_json(host, params):
        if params.get("list") == "search":
            return {"query": {"search": [{"title": t} for t in hits]}}
        return {"query": {"pages": [{"title": hits[0], "extract": extract}]}}
    return get_json


def test_research_uses_wikipedia_extract():
    m = research("광합성", get_json=wiki(["광합성", "광합성 세균"], "광합성은 빛에너지로 양분을 만드는 과정이다.\n== 과정 ==\n명반응"))
    assert m.title == "광합성" and "빛에너지" in m.markdown and "## 과정" in m.markdown
    assert m.sources == ["https://ko.wikipedia.org/wiki/%EA%B4%91%ED%95%A9%EC%84%B1"]


def test_research_nothing_found():
    with pytest.raises(OfficeError, match="못 찾았어"):
        research("ㅁㄴㅇㄹ", get_json=lambda host, params: {"query": {"search": []}})


# ---- 선생님 ----
def test_tutor_answers_from_material_with_feedback(tmp_path):
    seen = {}

    def llm(system, user, **kw):
        seen["system"], seen["user"] = system, user
        return "  미토콘드리아는 에너지를 만들어.  "
    path = answer_question("미토콘드리아가 뭐야?", CELL, tmp_path, llm=llm, feedback="더 쉽게")
    assert path.read_text(encoding="utf-8") == "미토콘드리아는 에너지를 만들어."
    assert "세포 호흡" in seen["user"] and "미토콘드리아가 뭐야?" in seen["user"] and "더 쉽게" in seen["user"]


def test_tutor_without_material_and_empty_answer(tmp_path):
    assert answer_question("1+1은?", None, tmp_path, llm=lambda s, u, **k: "2").read_text(encoding="utf-8") == "2"
    with pytest.raises(OfficeError):
        answer_question("뭐야?", None, tmp_path, llm=lambda s, u, **k: "  ")


# ---- 암기담당 ----
def test_validate_cards_dedupes_and_needs_three():
    raw = {"title": "세포", "cards": [{"front": "핵", "back": "유전 물질"}, {"front": "핵", "back": "중복"},
                                     {"front": "", "back": "x"}, {"front": "세포막", "back": "물질 출입"},
                                     {"front": "엽록체", "back": "광합성"}, "garbage"]}
    cards = validate_cards(raw)
    assert [c["front"] for c in cards["cards"]] == ["핵", "세포막", "엽록체"]
    with pytest.raises(OfficeError):
        validate_cards({"cards": [{"front": "a", "back": "b"}]})


def test_cards_page_csv_and_script_safety(tmp_path):
    raw = {"title": "세포 </script><script>alert(1)</script>",
           "cards": [{"front": f"용어{i}", "back": f"뜻{i}, \"따옴표\""} for i in range(30)]}
    page = make_cards_page(CELL, 10, tmp_path, llm=lambda s, u, schema, **k: raw)
    html = page.read_text(encoding="utf-8")
    assert "<script>alert(1)" not in html and page == tmp_path / "cards" / "index.html"
    rows = list(csv.reader((tmp_path / "cards" / "cards.csv").open(encoding="utf-8-sig")))
    assert len(rows) == 10 and rows[0] == ["용어0", "뜻0, \"따옴표\""]


# ---- 정리왕 ----
def test_validate_mindmap_limits_shape():
    raw = {"center": "세포", "branches": [
        {"label": f"가지{i}", "children": [{"label": f"잎{i}-{j}", "details": ["설명"] * 9} for j in range(9)]}
        for i in range(12)] + [{"label": "", "children": []}]}
    tree = validate_mindmap(raw)
    assert len(tree["branches"]) == 8 and len(tree["branches"][0]["children"]) == 6
    assert len(tree["branches"][0]["children"][0]["details"]) == 3
    with pytest.raises(OfficeError):
        validate_mindmap({"center": "x", "branches": []})


def test_mindmap_page_escapes(tmp_path):
    raw = {"center": "</script><b>세포</b>", "branches": [{"label": "핵", "children": []}, {"label": "막", "children": []}]}
    page = make_mindmap_page(CELL, tmp_path, llm=lambda s, u, schema, **k: raw)
    assert "</script><b>" not in page.read_text(encoding="utf-8")
    assert json.loads((tmp_path / "mindmap" / "mindmap.json").read_text(encoding="utf-8"))["center"] == "</script><b>세포</b>"


# ---- 비서 ----
def test_secretary_keeps_only_valid_items():
    raw = {"events": [{"title": "수학 학원", "date": "2026-10-22", "time": "15:00", "kind": "일정", "remind": 10, "repeat": "none"},
                      {"title": "날짜 이상", "date": "내일", "time": "", "kind": "일정", "remind": None, "repeat": "none"},
                      {"title": "기말고사", "date": "2026-11-20", "time": "", "kind": "파티", "remind": -5, "repeat": "yearly"}],
           "todos": [{"text": "영어 단어", "date": "", "time": "25:00"}, {"text": " ", "date": "", "time": ""}],
           "reply": "넣었어"}
    seen = {}

    def llm(system, user, schema, **kw):
        seen["user"] = user
        return raw
    out = parse_schedule("내일 3시 수학 학원, 기말고사 11월 20일, 영어 단어", TODAY, llm=llm)
    assert "2026-10-21(수)" in seen["user"] and "2026-10-22(목)" in seen["user"]
    assert [e["title"] for e in out["events"]] == ["수학 학원", "기말고사"]
    assert out["events"][1]["kind"] == "일정" and out["events"][1]["remind"] is None and out["events"][1]["repeat"] == "none"
    assert out["todos"] == [{"text": "영어 단어", "date": "2026-10-21", "time": ""}]


def test_secretary_nothing_understood():
    with pytest.raises(OfficeError):
        parse_schedule("음", TODAY, llm=lambda s, u, schema, **k: {"events": [], "todos": [], "reply": ""})


# ---- 코치 ----
def test_study_plan_filters_dates_and_caps():
    todos = [{"date": "2026-10-20", "text": "어제"}, {"date": "2026-10-22", "text": "1단원 복습"},
             {"date": "2027-05-01", "text": "너무 멀어"}, {"date": "2026-10-23", "text": ""}]
    todos += [{"date": "2026-10-24", "text": f"문제 {i}"} for i in range(80)]
    plan = make_study_plan("시험 대비 계획", TODAY, exams=[{"title": "과학 시험", "date": "2026-10-30"}],
                           material=CELL, llm=lambda s, u, schema, **k: {"todos": todos, "reply": "짰어"})
    assert plan["todos"][0] == {"date": "2026-10-22", "text": "1단원 복습"}
    assert len(plan["todos"]) == 60 and all(t["date"] >= "2026-10-21" for t in plan["todos"])


def test_note_and_quiz_carry_ceo_feedback():
    from office.note import make_note
    from office.quiz import make_quiz
    seen = []

    def llm(system, user, schema, **kw):
        seen.append(user)
        if "questions" in schema["properties"]:
            return {"title": "q", "questions": [{"kind": "ox", "question": f"문제{i}", "choices": [], "answer": "O",
                                                 "explanation": ""} for i in range(3)]}
        return {"title": "t", "subtitle": "", "sections": [{"heading": "h", "points": ["p"], "highlight": ""}],
                "key_terms": [], "summary": []}
    make_note(CELL, llm=llm, feedback="표를 더 넣어줘")
    make_quiz(CELL, 3, llm=llm, feedback="더 어렵게")
    assert "[대표 수정 요청] 표를 더 넣어줘" in seen[0] and "[대표 수정 요청] 더 어렵게" in seen[1]
