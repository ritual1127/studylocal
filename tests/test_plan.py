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
    assert normalize_plan({"steps": "pdf", "unknown": 1}, True).steps == ["scan", "analysis"]

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

def test_files_alone_get_an_analysis_but_actions_do_not():
    assert normalize_plan({"steps": []}, True).steps == ["scan", "analysis"]
    assert normalize_plan({"steps": ["schedule"]}, True).steps == ["scan", "schedule"]
    assert normalize_plan({"steps": ["quiz", "analysis"]}, True).steps == ["scan", "analysis", "quiz"]

def test_translate_needs_material_and_keeps_target_language():
    p = normalize_plan({"steps": ["literature", "translate"], "work_query": "어린 왕자", "target_lang": " 영어 "}, False)
    assert p.steps == ["literature", "translate"] and p.target_lang == "영어"
    assert normalize_plan({"steps": ["translate"]}, False).error.startswith("자료가 없어")

# ---- 실측에서 작은 모델(4B)이 틀린 것들: 코드로 바로잡는다 ----
def test_query_or_topic_without_its_source_step_gets_the_source():
    p = normalize_plan({"steps": ["quiz"], "work_query": "운수 좋은 날"}, False)
    assert p.steps == ["literature", "quiz"] and p.error is None
    p = normalize_plan({"steps": ["cards"], "topic": "광합성"}, False)
    assert p.steps == ["research", "cards"] and p.error is None

def test_reference_words_mean_previous_material():
    llm = lambda s, u, schema, **k: {"steps": ["cards", "cards"], "use_last": False}
    p = route("방금 자료로 암기카드 만들어줘", has_files=False, llm=llm)
    assert p.steps == ["cards"] and p.use_last is True and p.error is None
    assert route("암기카드 만들어줘", has_files=False, llm=llm).error  # 가리키는 말이 없으면 되묻기

def test_extra_analysis_dropped_unless_asked():
    llm = lambda s, u, schema, **k: {"steps": ["quiz", "analysis"], "work_query": "운수 좋은 날"}
    assert route("운수 좋은 날 가져와서 문제 5개 만들어줘", False, llm=llm).steps == ["literature", "quiz"]
    assert route("운수 좋은 날 분석하고 문제 내줘", False, llm=llm).steps == ["literature", "analysis", "quiz"]

def test_router_prompt_has_examples_for_questions():
    from office.plan import ROUTER_SYSTEM
    assert "이게 뭐야" not in ROUTER_SYSTEM and "광합성이 뭐야?" in ROUTER_SYSTEM

def test_extra_study_plan_dropped_unless_asked():
    llm = lambda s, u, schema, **k: {"steps": ["schedule", "plan"]}
    assert route("내일 3시 수학 학원 일정 넣어줘", False, llm=llm).steps == ["schedule"]
    assert route("기말고사 11월 20일인데 공부 계획 짜줘", False, llm=llm).steps == ["schedule", "plan"]

# ---- 실장 행동 (에이전트) ----
def test_actions_are_cleaned_and_unknown_dropped():
    raw = {"steps": [], "actions": [
        {"tool": "notify", "to": "phone", "message": " 굿나잇 "},
        {"tool": "remind", "minutes": 10, "message": "물 마시기"},
        {"tool": "remind", "time": "25:00", "message": "시간이 이상함"},
        {"tool": "remind", "time": "21:30", "message": "단어 복습"},
        {"tool": "hack", "message": "x"}, {"tool": "notify", "message": " "}, "garbage",
        {"tool": "setting", "key": "ai", "value": "careful"}, {"tool": "setting", "key": "password", "value": "x"},
        {"tool": "approve"}, {"tool": "today"}]}
    p = normalize_plan(raw, False)
    assert [a["tool"] for a in p.actions] == ["notify", "remind", "remind", "setting", "approve"]  # 최대 5개
    assert p.actions[0] == {"tool": "notify", "to": "phone", "message": "굿나잇"}
    assert p.actions[2]["time"] == "21:30" and p.actions[4]["job"] == "latest" and p.error is None
    assert normalize_plan({"steps": [], "actions": [{"tool": "notify", "message": "hi"}]}, False).actions[0]["to"] == "both"

def test_router_prompt_teaches_actions():
    from office.plan import ROUTER_SCHEMA, ROUTER_SYSTEM
    assert "notify" in ROUTER_SYSTEM and "굿나잇" in ROUTER_SYSTEM and "actions" in ROUTER_SCHEMA["required"]

# ---- 직원 지정 (@이름) ----
def test_assignee_keeps_only_that_staff_work():
    seen = {}

    def llm(system, user, schema, **kw):
        seen["user"] = user
        return {"steps": ["research", "pdf", "quiz"], "topic": "광합성"}
    p = route("광합성 문제 내줘", False, llm=llm, assignee="examiner")
    assert p.steps == ["research", "quiz"] and "quiz" in seen["user"]
    p = route("세종대왕", False, llm=lambda s, u, schema, **k: {"steps": []}, assignee="researcher")
    assert p.steps == ["research"] and p.topic == "세종대왕" and p.error is None  # 조사만, 노트는 안 붙임
    p = route("이거 읽어줘", False, llm=lambda s, u, schema, **k: {"steps": []}, assignee="scanner")
    assert p.error and "첨부" in p.error
    assert "배포" in route("배포해", False, llm=llm, assignee="deployer").error
    p = route("광합성이 뭐야", False, llm=lambda s, u, schema, **k: {"steps": ["pdf"]}, assignee="tutor")
    assert p.steps == ["answer"] and p.question == "광합성이 뭐야" and p.error is None

# ---- 실측에서 4B가 행동을 헷갈린 것들 ----
def fixed(steps, actions):
    return lambda s, u, schema, **k: {"steps": steps, "actions": actions}

def test_remind_prefers_clock_time_and_fills_missing_message():
    p = route("9시 반에 단어 복습하라고 알려줘", False, llm=fixed([], [{"tool": "remind", "minutes": 930, "time": "09:30"}]))
    assert p.actions == [{"tool": "remind", "time": "09:30", "message": "9시 반에 단어 복습하라고"}]
    p = route("10분 뒤에 물 마시라고 알려줘", False, llm=fixed([], [{"tool": "remind", "minutes": 10}]))
    assert p.actions == [{"tool": "remind", "minutes": 10, "message": "10분 뒤에 물 마시라고"}]

def test_focus_stop_and_start_do_not_fight():
    assert route("공부모드 꺼줘", False, llm=fixed(["focus"], [{"tool": "focus_stop"}])).steps == []
    p = route("25분 공부모드 켜줘", False, llm=fixed(["focus"], [{"tool": "focus_stop"}]))
    assert p.steps == ["focus"] and p.actions == []

def test_read_actions_only_for_questions_and_no_stray_steps():
    p = route("오늘 뭐 해야 돼?", False, llm=fixed(["schedule"], [{"tool": "today"}]))
    assert p.steps == [] and p.actions == [{"tool": "today"}]
    p = route("내일 오후 3시 수학 학원 일정 넣어줘", False, llm=fixed(["schedule"], [{"tool": "today"}]))
    assert p.steps == ["schedule"] and p.actions == []
    p = route("단어 외우기 다 했어", False, llm=fixed(["answer"], [{"tool": "todo_done", "message": "단어 외우기"}]))
    assert p.steps == [] and p.actions[0]["tool"] == "todo_done"
