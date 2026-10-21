import re
from dataclasses import dataclass, field

from office.llm import chat_json

STEPS = ("scan", "literature", "research", "schedule", "plan", "focus",
         "analysis", "pdf", "quiz", "cards", "mindmap", "translate", "answer")
SOURCES = ("scan", "literature", "research")
ACTIONS = ("schedule", "plan", "focus")
OUTPUTS = ("analysis", "pdf", "quiz", "cards", "mindmap", "translate", "answer")
NEEDS_MATERIAL = ("analysis", "pdf", "quiz", "cards", "mindmap", "translate")  # answer는 자료 없이도 답할 수 있다
# 작은 모델이 use_last를 놓쳐도 이런 말이 있으면 이전 자료를 쓴다 (첨부가 있으면 '이걸로'는 첨부 파일)
REFER_WORDS = ("방금", "아까", "이걸로", "그걸로", "이거로", "그거로", "이 자료", "그 자료", "같은 자료", "저번")
# 실장이 바로 하는 일 (에이전트 행동). 지우기처럼 되돌릴 수 없는 일은 없다 (화면 버튼으로만)
TOOLS = ("notify", "remind", "today", "jobs", "approve", "reject", "cancel", "rerun", "todo_done", "focus_stop", "setting")
SETTING_KEYS = ("ai", "pc", "phone", "job_done", "briefing")
MAX_ACTIONS = 5
TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
# 직원을 지정하면(@이름) 그 직원의 일만 한다 (실장=평소대로, 배포담당=버튼 안내)
STAFF_STEPS = {"secretary": ("schedule",), "scanner": ("scan",), "librarian": ("literature",), "researcher": ("research",),
               "analyst": ("analysis",), "designer": ("pdf",), "examiner": ("quiz",), "cards": ("cards",),
               "mapper": ("mindmap",), "tutor": ("answer",), "translator": ("translate",), "coach": ("plan", "focus")}
# 작은 모델이 행동과 단계를 헷갈릴 때 쓰는 말 단서
STOP_WORDS = ("꺼", "그만", "멈", "중지", "끝내")
ASK_WORDS = ("?", "뭐", "알려", "있어", "어때", "몇", "보여", "현황", "확인")
REGISTER_WORDS = ("넣", "등록", "추가", "잡아", "적어", "기록")
QUESTION_WORDS = ("?", "뭐", "왜", "어떻게", "무슨", "설명")
NO_MATERIAL = "자료가 없어. 프린트 사진을 첨부하거나, 작품·주제 이름을 알려주거나, 보관함에서 [이 자료로 더 하기]를 눌러줘."


@dataclass
class Plan:
    steps: list[str]
    title: str = ""
    work_query: str = ""
    topic: str = ""
    question: str = ""
    question_count: int = 10
    card_count: int = 15
    focus_minutes: int = 25
    target_lang: str = ""
    use_last: bool = False
    reply: str = ""
    error: str | None = None
    actions: list[dict] = field(default_factory=list)


ROUTER_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {"type": "array", "items": {"type": "string", "enum": list(STEPS)}},
        "title": {"type": "string"},
        "work_query": {"type": "string"},
        "topic": {"type": "string"},
        "question": {"type": "string"},
        "question_count": {"type": "integer"},
        "card_count": {"type": "integer"},
        "focus_minutes": {"type": "integer"},
        "target_lang": {"type": "string"},
        "use_last": {"type": "boolean"},
        "actions": {"type": "array", "items": {
            "type": "object",
            "properties": {"tool": {"type": "string", "enum": list(TOOLS)},
                           "to": {"type": "string", "enum": ["phone", "pc", "both"]},
                           "message": {"type": "string"}, "minutes": {"type": "integer"}, "time": {"type": "string"},
                           "job": {"type": "string"}, "comment": {"type": "string"},
                           "key": {"type": "string", "enum": list(SETTING_KEYS)}, "value": {"type": "string"}},
            "required": ["tool"]}},
        "reply": {"type": "string"},
    },
    "required": ["steps", "title", "work_query", "topic", "question", "question_count", "card_count",
                 "focus_minutes", "target_lang", "use_last", "actions", "reply"],
}

ROUTER_SYSTEM = """너는 'ritual의 공부 사무실'의 실장이다. 대표(사용자)의 요청을 보고 직원들에게 맡길 단계를 고른다.
자료 단계:
- scan: 첨부한 파일(사진·PDF·한글·워드·PPT·엑셀·글자 파일)을 읽는다 (첨부 파일이 있을 때만)
- literature: 문학 작품(소설·시·수필)의 원문과 해설을 가져온다. work_query에 작품 제목, 작가를 알면 함께
- research: 문학이 아닌 주제(개념·인물·사건·과학 등)를 조사한다. topic에 주제
결과 단계 (answer 말고는 자료가 필요하다):
- answer: 질문에 답한다. question에 질문 ("~가 뭐야?", "~ 설명해줘", "왜 ~야?")
- analysis: 자료 분석 보고서. "분석해줘"라고 할 때만
- pdf: 자료를 예쁜 공부 노트 PDF로
- quiz: 문제 풀이 웹. question_count에 문제 수 (말이 없으면 10)
- cards: 암기카드. card_count에 카드 수 (말이 없으면 15)
- mindmap: 개념 마인드맵
- translate: 자료 번역. target_lang에 언어 (말이 없으면 빈 문자열)
행동 단계:
- schedule: 일정·할 일·시험 날짜를 등록한다
- plan: 시험 대비 공부 계획을 날짜별 할 일로 짠다
- focus: 공부모드(집중 타이머)를 켠다. focus_minutes (말이 없으면 25)
실장이 바로 하는 일 (actions, 여러 개 가능, 없으면 빈 배열):
- notify: 대표에게 메시지 보내기. to는 phone(폰)·pc(PC)·both(둘 다), message에 보낼 말
- remind: 나중에 알려주기. minutes(몇 분 뒤) 또는 time(HH:MM), message에 알릴 말
- today: 오늘 할 일·일정·시험 알려주기 / jobs: 작업·결재 현황 알려주기
- approve·reject: 결재. job은 latest(방금 것)·all(전부)·작업 번호, reject는 comment에 고칠 점
- cancel: 작업 중단 / rerun: 작업 처음부터 다시 (job은 latest·all·번호)
- todo_done: 할 일을 했다고 체크 (message에 할 일 이름) / focus_stop: 공부모드 끄기
- setting: 설정 바꾸기. key는 ai(value fast·careful)·pc·phone·job_done(value on·off)·briefing(value HH:MM 또는 off)
"방금 자료로", "아까 그걸로"처럼 이전 자료를 쓰라는 말이면 use_last를 true로 한다.
배포해 달라는 말이 있어도 단계에 넣지 않는다 (배포는 대표가 결재 후 화면 버튼으로 한다).
title에는 결과물에 붙일 짧은 제목, reply에는 실장으로서 반말로 한두 문장 대답을 쓴다.
할 일이 없는 인사나 잡담이면 steps를 빈 배열로 둔다. 시키지 않은 단계는 넣지 않는다.
예시 (요청 → steps):
- "광합성이 뭐야?" → ["answer"], question "광합성이 뭐야?"
- "운수 좋은 날 가져와서 문제 5개" → ["literature", "quiz"], work_query "운수 좋은 날", question_count 5
- "광합성 조사해서 암기카드랑 마인드맵" → ["research", "cards", "mindmap"], topic "광합성"
- (첨부) "이 프린트 분석해줘" → ["scan", "analysis"]
- (첨부) "PDF로 만들고 영어로 번역해줘" → ["scan", "pdf", "translate"], target_lang "영어"
- "방금 자료로 암기카드" → ["cards"], use_last true
- "내일 3시 수학 학원, 할 일에 단어 외우기" → ["schedule"]
- "기말고사 11월 20일인데 공부 계획 짜줘" → ["schedule", "plan"]
- "25분 공부모드 켜줘" → ["focus"], focus_minutes 25
- "내 폰으로 굿나잇이라고 보내" → steps [], actions [{"tool": "notify", "to": "phone", "message": "굿나잇"}]
- "10분 뒤에 물 마시라고 알려줘" → steps [], actions [{"tool": "remind", "minutes": 10, "message": "물 마시기"}]
- "오늘 뭐 해야 돼?" → steps [], actions [{"tool": "today"}]
- "방금 거 승인해" → steps [], actions [{"tool": "approve", "job": "latest"}]
- "단어 외우기 다 했어" → steps [], actions [{"tool": "todo_done", "message": "단어 외우기"}]
- "꼼꼼 모드로 바꿔" → steps [], actions [{"tool": "setting", "key": "ai", "value": "careful"}]
JSON으로만 답한다."""


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _count(value, default: int, low: int, high: int) -> int:
    try:
        count = int(value or default)
    except (TypeError, ValueError):
        count = default
    return max(low, min(high, count))


def _said(text: str) -> str:
    """'…라고 알려줘'에서 알릴 말만 (작은 모델이 message를 빼먹을 때)."""
    return re.sub(r"\s*(알려\s*줘|말해\s*줘|해\s*줘)[.!~]*$", "", text.strip()) or text.strip()


def _clean_actions(items, text: str = "") -> list[dict]:
    out = []
    for a in items if isinstance(items, list) else []:
        if not isinstance(a, dict) or a.get("tool") not in TOOLS:
            continue
        tool, message = a["tool"], " ".join(_text(a.get("message")).split())[:300]
        act = {"tool": tool}
        if tool in ("remind", "todo_done") and not message and text:
            message = _said(text)[:300]
        if tool == "notify":
            if not message:
                continue
            act.update(to=a.get("to") if a.get("to") in ("phone", "pc", "both") else "both", message=message)
        elif tool == "remind":
            minutes, time = a.get("minutes"), _text(a.get("time"))
            if not message:
                continue
            if TIME.fullmatch(time):  # "9시 반"을 분(930)과 시각 둘 다로 쓰면 시각을 믿는다
                act.update(time=time, message=message)
            elif isinstance(minutes, int) and not isinstance(minutes, bool) and 1 <= minutes <= 1440:
                act.update(minutes=minutes, message=message)
            else:
                continue
        elif tool in ("approve", "reject", "cancel", "rerun"):
            act["job"] = _text(a.get("job"))[:40] or "latest"
            if tool in ("approve", "reject"):
                act["comment"] = _text(a.get("comment"))[:500]
        elif tool == "todo_done":
            if not message:
                continue
            act["message"] = message
        elif tool == "setting":
            if a.get("key") not in SETTING_KEYS or not _text(a.get("value")):
                continue
            act.update(key=a["key"], value=_text(a["value"])[:20])
        out.append(act)
    return out[:MAX_ACTIONS]


def normalize_plan(raw: dict, has_files: bool, has_ref: bool = False, text: str = "") -> Plan:
    wanted = raw.get("steps")
    wanted = wanted if isinstance(wanted, list) else []
    steps = [s for s in STEPS if s in wanted]
    if has_files and "scan" not in steps:
        steps.insert(0, "scan")
    if not has_files and "scan" in steps:
        steps.remove("scan")
    work_query, topic = _text(raw.get("work_query")), _text(raw.get("topic"))
    if not work_query and "literature" in steps:
        steps.remove("literature")
    if not topic and "research" in steps:
        steps.remove("research")
    use_last = raw.get("use_last") is True and not has_files
    if any(s in NEEDS_MATERIAL for s in steps) and not any(s in SOURCES for s in steps) and not has_ref and not use_last:
        if work_query:  # 작품·주제 이름은 적고 가져오는 단계를 빠뜨렸다 (작은 모델이 자주 그런다)
            steps.insert(0, "literature")
        elif topic:
            steps.insert(0, "research")
    if "research" in steps and not any(s in OUTPUTS or s in ACTIONS for s in steps):
        steps.append("pdf")  # 조사만 시키면 노트로 정리해 준다
    if has_files and not any(s in OUTPUTS or s in ACTIONS for s in steps):
        steps.append("analysis")  # 파일만 올리면 분석해 준다
    error = None
    if (any(s in NEEDS_MATERIAL for s in steps) and not any(s in SOURCES for s in steps)
            and not has_ref and not use_last):
        error = NO_MATERIAL
    reply = _text(raw.get("reply")) or (
        "알겠어, 시작할게!" if steps else "뭘 도와줄까? 프린트를 올리거나 작품 이름을 말해줘.")
    return Plan(steps=steps, title=_text(raw.get("title")) or work_query or topic, work_query=work_query,
                topic=topic, question=_text(raw.get("question")),
                question_count=_count(raw.get("question_count"), 10, 3, 20),
                card_count=_count(raw.get("card_count"), 15, 5, 40),
                focus_minutes=_count(raw.get("focus_minutes"), 25, 1, 180),
                target_lang=_text(raw.get("target_lang"))[:20],
                use_last=use_last, reply=reply, error=error, actions=_clean_actions(raw.get("actions"), text))


def _untangle(plan: Plan, text: str) -> None:
    """작은 모델이 행동과 단계를 같이 붙여 서로 엇갈리는 것들을 말 단서로 정리한다."""
    tools = {a["tool"] for a in plan.actions}
    if "focus_stop" in tools and "focus" in plan.steps:
        if any(w in text for w in STOP_WORDS):
            plan.steps.remove("focus")  # "꺼줘"인데 공부모드를 다시 켜지 않게
        else:
            plan.actions = [a for a in plan.actions if a["tool"] != "focus_stop"]
    if tools & {"today", "jobs"} and not any(w in text for w in ASK_WORDS):
        plan.actions = [a for a in plan.actions if a["tool"] not in ("today", "jobs")]  # 묻지 않았으면 현황을 늘어놓지 않는다
    elif tools & {"today", "jobs"} and "schedule" in plan.steps and not any(w in text for w in REGISTER_WORDS):
        plan.steps.remove("schedule")  # "오늘 뭐 해?"는 등록이 아니라 묻는 말
    if plan.actions and "answer" in plan.steps and not any(w in text for w in QUESTION_WORDS):
        plan.steps.remove("answer")  # "다 했어" 같은 보고에 선생님이 답하지 않게


def _assign(plan: Plan, allowed: tuple, text: str, has_files: bool, has_ref: bool) -> Plan:
    """대표가 직원을 지정했다: 그 직원 일 + 필요한 자료 단계만 남긴다."""
    keep = {s for s in plan.steps if s in SOURCES or s in allowed}
    if not keep & set(allowed):
        keep.add(allowed[0])
    plan.steps = [s for s in STEPS if s in keep]
    if "literature" in keep and not plan.work_query:
        plan.work_query = text
    if "research" in keep and not plan.topic:
        plan.topic = text
    if "answer" in keep and not plan.question:
        plan.question = text
    plan.error = None
    if "scan" in keep and not has_files:
        plan.error = "스캐너한테 줄 파일을 첨부해줘."
    elif (any(s in NEEDS_MATERIAL for s in keep) and not keep & set(SOURCES) and not has_ref and not plan.use_last):
        plan.error = NO_MATERIAL
    return plan


def route(text: str, has_files: bool, llm=chat_json, has_ref: bool = False, assignee: str = "") -> Plan:
    if assignee == "deployer":
        return Plan(steps=[], error="배포는 대표가 승인한 작업 카드의 [배포] 버튼으로 해줘.")
    allowed = STAFF_STEPS.get(assignee)
    user = (f"요청: {text}\n첨부 파일: {'있음' if has_files else '없음'}\n"
            f"선택한 이전 자료: {'있음' if has_ref else '없음'}")
    if allowed:
        user += f"\n대표가 직원을 지정했다. 그 직원의 일: {', '.join(allowed)} (이 단계와 필요한 자료 단계만 고른다)"
    raw = llm(ROUTER_SYSTEM, user, ROUTER_SCHEMA, temperature=0)
    if not has_files and not has_ref and any(w in text for w in REFER_WORDS):
        raw = {**raw, "use_last": True}
    plan = normalize_plan(raw, has_files, has_ref, text)
    _untangle(plan, text)
    if "analysis" in plan.steps and "분석" not in text and any(s in OUTPUTS and s != "analysis" for s in plan.steps):
        plan.steps.remove("analysis")  # 시키지 않은 분석은 뺀다 (작은 모델이 덤으로 붙인다)
    if "plan" in plan.steps and "계획" not in text:
        plan.steps.remove("plan")  # 일정만 말했는데 공부 계획까지 짜지 않는다
    if allowed:
        plan = _assign(plan, allowed, text, has_files, has_ref)
    if "answer" in plan.steps and not plan.question:
        plan.question = text
    return plan
