from dataclasses import dataclass

from office.llm import chat_json

STEPS = ("scan", "literature", "pdf", "quiz")
SOURCES = ("scan", "literature")
OUTPUTS = ("pdf", "quiz")


@dataclass
class Plan:
    steps: list[str]
    title: str = ""
    work_query: str = ""
    question_count: int = 10
    reply: str = ""
    error: str | None = None


ROUTER_SCHEMA = {
    "type": "object",
    "properties": {
        "steps": {"type": "array", "items": {"type": "string", "enum": list(STEPS)}},
        "title": {"type": "string"},
        "work_query": {"type": "string"},
        "question_count": {"type": "integer"},
        "reply": {"type": "string"},
    },
    "required": ["steps", "title", "work_query", "question_count", "reply"],
}

ROUTER_SYSTEM = """너는 'ritual의 공부 사무실'의 실장이다. 사용자의 요청을 보고 직원들에게 맡길 단계를 고른다.
- scan: 첨부한 프린트·사진·PDF를 읽는다 (첨부 파일이 있을 때만)
- literature: 문학 작품의 원문과 해설을 가져온다. work_query에 작품 제목을 쓰고, 작가를 알면 함께 쓴다
- pdf: 자료를 예쁜 공부 노트 PDF로 만든다
- quiz: 자료로 문제 풀이 웹을 만든다. question_count에 문제 수 (말이 없으면 10)
배포해 달라는 말이 있어도 단계에 넣지 않는다 (배포는 사용자가 화면의 버튼으로 한다).
title에는 결과물에 붙일 짧은 제목, reply에는 실장으로서 반말로 한두 문장 대답을 쓴다.
할 일이 없는 인사나 잡담이면 steps를 빈 배열로 둔다. JSON으로만 답한다."""


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def normalize_plan(raw: dict, has_files: bool) -> Plan:
    wanted = raw.get("steps")
    wanted = wanted if isinstance(wanted, list) else []
    steps = [s for s in STEPS if s in wanted]
    if has_files and "scan" not in steps:
        steps.insert(0, "scan")
    if not has_files and "scan" in steps:
        steps.remove("scan")
    work_query = _text(raw.get("work_query"))
    if not work_query and "literature" in steps:
        steps.remove("literature")
    try:
        count = int(raw.get("question_count") or 10)
    except (TypeError, ValueError):
        count = 10
    count = max(3, min(20, count))
    error = None
    if any(s in OUTPUTS for s in steps) and not any(s in SOURCES for s in steps):
        error = "자료가 없어. 프린트 사진을 첨부하거나 작품 이름을 알려줘."
    reply = _text(raw.get("reply")) or (
        "알겠어, 시작할게!" if steps else "뭘 도와줄까? 프린트를 올리거나 작품 이름을 말해줘.")
    return Plan(steps=steps, title=_text(raw.get("title")) or work_query, work_query=work_query,
                question_count=count, reply=reply, error=error)


def route(text: str, has_files: bool, llm=chat_json) -> Plan:
    user = f"요청: {text}\n첨부 파일: {'있음' if has_files else '없음'}"
    return normalize_plan(llm(ROUTER_SYSTEM, user, ROUTER_SCHEMA, temperature=0), has_files)
