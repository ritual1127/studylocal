from dataclasses import dataclass

from office.llm import chat_json

STEPS = ("scan", "literature", "research", "schedule", "plan", "focus", "pdf", "quiz", "cards", "mindmap", "answer")
SOURCES = ("scan", "literature", "research")
OUTPUTS = ("pdf", "quiz", "cards", "mindmap", "answer")
NEEDS_MATERIAL = ("pdf", "quiz", "cards", "mindmap")  # answer는 자료 없이도 답할 수 있다


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
    use_last: bool = False
    reply: str = ""
    error: str | None = None


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
        "use_last": {"type": "boolean"},
        "reply": {"type": "string"},
    },
    "required": ["steps", "title", "work_query", "topic", "question", "question_count", "card_count",
                 "focus_minutes", "use_last", "reply"],
}

ROUTER_SYSTEM = """너는 'ritual의 공부 사무실'의 실장이다. 대표(사용자)의 요청을 보고 직원들에게 맡길 단계를 고른다.
자료 단계:
- scan: 첨부한 프린트·사진·PDF를 읽는다 (첨부 파일이 있을 때만)
- literature: 문학 작품(소설·시·수필)의 원문과 해설을 가져온다. work_query에 작품 제목, 작가를 알면 함께
- research: 문학이 아닌 주제(개념·인물·사건·과학 등)를 조사한다. topic에 주제
결과 단계 (pdf·quiz·cards·mindmap은 자료가 필요하고, answer는 자료 없이도 된다):
- pdf: 자료를 예쁜 공부 노트 PDF로
- quiz: 문제 풀이 웹. question_count에 문제 수 (말이 없으면 10)
- cards: 암기카드. card_count에 카드 수 (말이 없으면 15)
- mindmap: 개념 마인드맵
- answer: 질문에 답한다. question에 질문
행동 단계:
- schedule: 일정·할 일·시험 날짜를 등록한다 ("내일 3시 학원", "할 일에 단어 외우기 넣어줘", "기말고사 11월 20일")
- plan: 시험 대비 공부 계획을 날짜별 할 일로 짠다
- focus: 공부모드(집중 타이머)를 켠다. focus_minutes (말이 없으면 25)
"방금 자료로", "아까 그걸로"처럼 이전 자료를 쓰라는 말이면 use_last를 true로 한다.
배포해 달라는 말이 있어도 단계에 넣지 않는다 (배포는 대표가 결재 후 화면 버튼으로 한다).
title에는 결과물에 붙일 짧은 제목, reply에는 실장으로서 반말로 한두 문장 대답을 쓴다.
할 일이 없는 인사나 잡담이면 steps를 빈 배열로 둔다. JSON으로만 답한다."""


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _count(value, default: int, low: int, high: int) -> int:
    try:
        count = int(value or default)
    except (TypeError, ValueError):
        count = default
    return max(low, min(high, count))


def normalize_plan(raw: dict, has_files: bool, has_ref: bool = False) -> Plan:
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
    if "research" in steps and not any(s in OUTPUTS or s in ("schedule", "plan", "focus") for s in steps):
        steps.append("pdf")  # 조사만 시키면 노트로 정리해 준다
    use_last = raw.get("use_last") is True
    error = None
    if (any(s in NEEDS_MATERIAL for s in steps) and not any(s in SOURCES for s in steps)
            and not has_ref and not use_last):
        error = "자료가 없어. 프린트 사진을 첨부하거나, 작품·주제 이름을 알려주거나, 보관함에서 [이 자료로 더 하기]를 눌러줘."
    reply = _text(raw.get("reply")) or (
        "알겠어, 시작할게!" if steps else "뭘 도와줄까? 프린트를 올리거나 작품 이름을 말해줘.")
    return Plan(steps=steps, title=_text(raw.get("title")) or work_query or topic, work_query=work_query,
                topic=topic, question=_text(raw.get("question")),
                question_count=_count(raw.get("question_count"), 10, 3, 20),
                card_count=_count(raw.get("card_count"), 15, 5, 40),
                focus_minutes=_count(raw.get("focus_minutes"), 25, 1, 180),
                use_last=use_last, reply=reply, error=error)


def route(text: str, has_files: bool, llm=chat_json, has_ref: bool = False) -> Plan:
    user = (f"요청: {text}\n첨부 파일: {'있음' if has_files else '없음'}\n"
            f"선택한 이전 자료: {'있음' if has_ref else '없음'}")
    plan = normalize_plan(llm(ROUTER_SYSTEM, user, ROUTER_SCHEMA, temperature=0), has_files, has_ref)
    if "answer" in plan.steps and not plan.question:
        plan.question = text
    return plan
