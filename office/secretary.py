"""비서: 말로 한 일정·할 일을 플래너 항목으로 정리한다."""
import datetime as dt

from office import OfficeError
from office.llm import chat_json
from office.planner import KINDS, REPEATS, TIME, WEEKDAYS

SCHEDULE_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {"type": "array", "items": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "date": {"type": "string"}, "time": {"type": "string"},
                           "kind": {"type": "string", "enum": list(KINDS)},
                           "remind": {"type": ["integer", "null"]},
                           "repeat": {"type": "string", "enum": list(REPEATS)}},
            "required": ["title", "date", "time", "kind", "remind", "repeat"]}},
        "todos": {"type": "array", "items": {
            "type": "object",
            "properties": {"text": {"type": "string"}, "date": {"type": "string"}, "time": {"type": "string"}},
            "required": ["text", "date", "time"]}},
        "reply": {"type": "string"},
    },
    "required": ["events", "todos", "reply"],
}

SECRETARY_SYSTEM = """너는 '공부 사무실'의 비서 직원이다. 요청에서 일정과 할 일을 뽑아 정리한다.
- events: 정해진 날짜·시간에 있는 일(학원, 약속, 시험, 숙제 마감). kind는 일정·시험·숙제 중 하나.
  date는 YYYY-MM-DD, time은 HH:MM(24시간, 모르면 빈 문자열). remind는 몇 분 전에 알릴지(시간이 있으면 기본 10, 없으면 null).
  repeat은 none·daily·weekly ("매주"면 weekly).
- todos: 해야 할 일. date는 YYYY-MM-DD(말이 없으면 오늘), time은 알림 받을 시각(없으면 빈 문자열).
- "내일", "다음 주 화요일" 같은 말은 아래 달력을 보고 정확한 날짜로 바꾼다. 오후 3시 = 15:00.
reply에는 비서로서 반말로 한 문장 대답. JSON으로만 답한다."""


def _calendar(today: dt.date) -> str:
    days = [today + dt.timedelta(days=i) for i in range(15)]
    return " ".join(f"{d.isoformat()}({WEEKDAYS[d.weekday()]})" for d in days)


def _date(value, today: dt.date) -> str | None:
    if not value:
        return today.isoformat()
    try:
        return dt.date.fromisoformat(str(value)).isoformat()
    except ValueError:
        return None


def parse_schedule(text: str, today: dt.date, llm=chat_json) -> dict:
    user = f"오늘: {today.isoformat()}({WEEKDAYS[today.weekday()]})\n달력: {_calendar(today)}\n\n요청: {text}"
    raw = llm(SECRETARY_SYSTEM, user, SCHEDULE_SCHEMA, temperature=0)
    events, todos = [], []
    for ev in raw.get("events") or []:
        if not isinstance(ev, dict) or not str(ev.get("title") or "").strip() or not ev.get("date"):
            continue
        date = _date(ev.get("date"), today)
        if date is None:
            continue
        time = str(ev.get("time") or "").strip()
        remind = ev.get("remind")
        events.append({"title": " ".join(str(ev["title"]).split())[:100], "date": date,
                       "time": time if TIME.fullmatch(time) else "",
                       "kind": ev.get("kind") if ev.get("kind") in KINDS else "일정",
                       "remind": remind if isinstance(remind, int) and not isinstance(remind, bool) and 0 <= remind <= 10080 else None,
                       "repeat": ev.get("repeat") if ev.get("repeat") in REPEATS else "none"})
    for td in raw.get("todos") or []:
        text_ = " ".join(str(td.get("text") or "").split()) if isinstance(td, dict) else ""
        date = _date(td.get("date"), today) if text_ else None
        if not text_ or date is None:
            continue
        time = str(td.get("time") or "").strip()
        todos.append({"text": text_[:200], "date": date, "time": time if TIME.fullmatch(time) else ""})
    if not events and not todos:
        raise OfficeError("일정이나 할 일을 못 알아들었어. '내일 3시 수학 학원'처럼 말해줘.")
    return {"events": events, "todos": todos, "reply": str(raw.get("reply") or "").strip()}
