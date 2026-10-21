"""코치: 시험 대비 공부 계획을 날짜별 할 일로 짠다 (공부모드 타이머는 플래너가 잰다)."""
import datetime as dt

from office import Material, OfficeError
from office.llm import chat_json, clip
from office.planner import WEEKDAYS

MAX_PLAN = 60
PLAN_DAYS = 60

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "todos": {"type": "array", "items": {
            "type": "object",
            "properties": {"date": {"type": "string"}, "text": {"type": "string"}},
            "required": ["date", "text"]}},
        "reply": {"type": "string"},
    },
    "required": ["todos", "reply"],
}

COACH_SYSTEM = """너는 '공부 사무실'의 공부 코치 직원이다. 학생이 시험까지 무엇을 언제 공부할지 날짜별 할 일로 계획한다.
- 하루에 할 일은 1~3개, 한 개는 짧은 한 문장(예: "2단원 개념 정리 + 문제 10개").
- 오늘부터 시험 전날까지 고르게 나누고, 마지막 2~3일은 전체 복습·오답 정리로.
- date는 YYYY-MM-DD. 자료가 있으면 자료의 단원·개념 이름을 쓴다.
reply에는 코치로서 반말로 응원 한두 문장. JSON으로만 답한다."""


def make_study_plan(text: str, today: dt.date, exams: list[dict], material: Material | None = None,
                    llm=chat_json) -> dict:
    lines = [f"오늘: {today.isoformat()}({WEEKDAYS[today.weekday()]})", f"요청: {text}"]
    if exams:
        lines.append("다가오는 시험: " + ", ".join(f"{e['title']} {e['date']}" for e in exams))
    if material:
        lines.append(f"[공부 자료: {material.title}]\n{clip(material.markdown, 3000)}")
    raw = llm(COACH_SYSTEM, "\n".join(lines), PLAN_SCHEMA, temperature=0.2)
    last = today + dt.timedelta(days=PLAN_DAYS)
    todos = []
    for item in raw.get("todos") or []:
        if not isinstance(item, dict):
            continue
        task = " ".join(str(item.get("text") or "").split())[:100]
        try:
            day = dt.date.fromisoformat(str(item.get("date")))
        except ValueError:
            continue
        if task and today <= day <= last:
            todos.append({"date": day.isoformat(), "text": task})
    if not todos:
        raise OfficeError("계획을 못 짰어. 시험 날짜와 과목을 같이 말해줘.")
    todos.sort(key=lambda t: t["date"])
    return {"todos": todos[:MAX_PLAN], "reply": str(raw.get("reply") or "").strip()}
