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

def test_new_steps_ordered_and_research_needs_topic():
    p = normalize_plan({"steps": ["answer", "research", "cards"], "topic": " 광합성 "}, False)
    assert p.steps == ["research", "cards", "answer"] and p.topic == "광합성" and p.error is None
    assert normalize_plan({"steps": ["research", "cards"], "topic": ""}, False).error.startswith("자료가 없어")

def test_answer_needs_no_material_and_question_defaults_to_text():
    p = route("광합성이 뭐야?", has_files=False, llm=lambda s, u, schema, **k: {"steps": ["answer"], "question": ""})
    assert p.steps == ["answer"] and p.error is None and p.question == "광합성이 뭐야?"

def test_ref_or_use_last_counts_as_material():
    assert normalize_plan({"steps": ["quiz"]}, False, has_ref=True).error is None
    p = normalize_plan({"steps": ["cards"], "use_last": True}, False)
    assert p.use_last is True and p.error is None

def test_research_alone_gets_a_note():
    assert normalize_plan({"steps": ["research"], "topic": "광합성"}, False).steps == ["research", "pdf"]

def test_counts_clamped_with_defaults():
    p = normalize_plan({"steps": ["focus", "cards"], "focus_minutes": 500, "card_count": 100}, True)
    assert p.focus_minutes == 180 and p.card_count == 40
    p = normalize_plan({"steps": ["focus"]}, False)
    assert p.focus_minutes == 25 and p.card_count == 15 and p.error is None

def test_route_tells_router_about_selected_material():
    seen = {}
    def fake(system, user, schema, **kw):
        seen["user"] = user
        return {"steps": ["cards"]}
    assert route("이걸로 카드", has_files=False, llm=fake, has_ref=True).error is None
    assert "선택한 이전 자료: 있음" in seen["user"]
