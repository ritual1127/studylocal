"""플래너: 오늘 할 일, 일정, 공부모드 기록, 그리고 때가 된 알림 고르기."""
import datetime as dt
import json
import re
import secrets
import threading
from pathlib import Path

from office import OfficeError

KINDS = ("일정", "시험", "숙제")
REPEATS = ("none", "daily", "weekly")
WEEKDAYS = "월화수목금토일"
TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
LATE = dt.timedelta(minutes=10)  # 꺼져 있던 동안 지난 알림은 10분 안의 것만
MAX_FIRED = 300


def _date(value, default: str | None = None) -> str:
    if not value:
        if default is None:
            raise OfficeError("날짜를 알려줘.")
        return default
    try:
        return dt.date.fromisoformat(str(value)).isoformat()
    except ValueError:
        raise OfficeError("날짜는 2026-10-21처럼 써줘.") from None


def _time(value) -> str:
    value = str(value or "").strip()
    if value and not TIME.fullmatch(value):
        raise OfficeError("시간은 15:30처럼 써줘.")
    return value


def _text(value, limit: int = 200) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise OfficeError("내용을 적어줘.")
    return text[:limit]


def occurs_on(event: dict, day: dt.date) -> bool:
    start = dt.date.fromisoformat(event["date"])
    if day < start:
        return False
    if event["repeat"] == "daily":
        return True
    if event["repeat"] == "weekly":
        return (day - start).days % 7 == 0
    return day == start


class Planner:
    def __init__(self, path: Path, now=dt.datetime.now):
        self.path, self.now = Path(path), now
        self.lock = threading.RLock()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        focus = data.get("focus") if isinstance(data.get("focus"), dict) else {}
        self.data = {"todos": list(data.get("todos") or []), "events": list(data.get("events") or []),
                     "focus": {"running": focus.get("running"), "log": list(focus.get("log") or [])},
                     "fired": list(data.get("fired") or [])}

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")  # 쓰다가 꺼져도 원래 파일은 멀쩡하게
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def _today(self) -> dt.date:
        return self.now().date()

    def _find(self, kind: str, item_id: str) -> dict:
        for item in self.data[kind]:
            if item["id"] == item_id:
                return item
        raise OfficeError("그런 할 일이 없어." if kind == "todos" else "그런 일정이 없어.")

    # ---- 할 일 ----
    def add_todo(self, text, date="", time="") -> dict:
        todo = {"id": secrets.token_hex(4), "text": _text(text), "date": _date(date, self._today().isoformat()),
                "time": _time(time), "done": False}
        with self.lock:
            self.data["todos"].append(todo)
            self._save()
        return dict(todo)

    def update_todo(self, todo_id: str, changes: dict) -> dict:
        with self.lock:
            todo = self._find("todos", todo_id)
            new = dict(todo)
            if "done" in changes:
                if not isinstance(changes["done"], bool):
                    raise OfficeError("완료 값이 이상해.")
                new["done"] = changes["done"]
            if "text" in changes:
                new["text"] = _text(changes["text"])
            if "date" in changes:
                new["date"] = _date(changes["date"])
            if "time" in changes:
                new["time"] = _time(changes["time"])
            todo.update(new)
            self._save()
            return dict(todo)

    def delete_todo(self, todo_id: str) -> None:
        with self.lock:
            self.data["todos"].remove(self._find("todos", todo_id))
            self._save()

    # ---- 일정 ----
    def add_event(self, title, date, time="", kind="일정", remind=None, repeat="none") -> dict:
        if kind not in KINDS:
            raise OfficeError("일정 종류는 일정·시험·숙제 중 하나야.")
        if repeat not in REPEATS:
            raise OfficeError("반복은 안 함·매일·매주 중 하나야.")
        if remind is not None and (not isinstance(remind, int) or isinstance(remind, bool) or not 0 <= remind <= 10080):
            raise OfficeError("알림은 0~10080분 전 사이로 골라줘.")
        event = {"id": secrets.token_hex(4), "title": _text(title, 100), "date": _date(date), "time": _time(time),
                 "kind": kind, "remind": remind, "repeat": repeat}
        with self.lock:
            self.data["events"].append(event)
            self._save()
        return dict(event)

    def delete_event(self, event_id: str) -> None:
        with self.lock:
            self.data["events"].remove(self._find("events", event_id))
            self._save()

    # ---- 공부모드 ----
    def start_focus(self, minutes, task="", kind="focus") -> dict:
        if not isinstance(minutes, int) or isinstance(minutes, bool) or not 1 <= minutes <= 180:
            raise OfficeError("공부 시간은 1~180분으로 골라줘.")
        if kind not in ("focus", "break"):
            raise OfficeError("공부모드 종류가 이상해.")
        start = self.now().replace(microsecond=0)
        running = {"kind": kind, "task": " ".join(str(task or "").split())[:100], "minutes": minutes,
                   "start": start.isoformat(), "end": (start + dt.timedelta(minutes=minutes)).isoformat()}
        with self.lock:
            self.data["focus"]["running"] = running
            self._save()
        return dict(running)

    def _log_focus(self, running: dict, minutes: int) -> None:
        if running["kind"] == "focus" and minutes >= 1:
            self.data["focus"]["log"].append({"date": running["start"][:10], "minutes": minutes, "task": running["task"]})

    def stop_focus(self) -> int:
        with self.lock:
            running = self.data["focus"]["running"]
            if not running:
                return 0
            elapsed = self.now() - dt.datetime.fromisoformat(running["start"])
            minutes = min(running["minutes"], int(elapsed.total_seconds() // 60))
            self._log_focus(running, minutes)
            self.data["focus"]["running"] = None
            self._save()
            return minutes

    # ---- 보기 ----
    def _stats(self, today: dt.date) -> dict:
        per_day: dict[str, int] = {}
        for entry in self.data["focus"]["log"]:
            per_day[entry["date"]] = per_day.get(entry["date"], 0) + entry["minutes"]
        week = [{"date": d.isoformat(), "minutes": per_day.get(d.isoformat(), 0)}
                for d in (today - dt.timedelta(days=i) for i in range(6, -1, -1))]
        day, streak = today if per_day.get(today.isoformat()) else today - dt.timedelta(days=1), 0
        while per_day.get(day.isoformat()):
            streak += 1
            day -= dt.timedelta(days=1)
        return {"today": per_day.get(today.isoformat(), 0), "week": week, "streak": streak}

    def view(self) -> dict:
        with self.lock:
            now = self.now()
            today = now.date()
            iso = today.isoformat()
            todos = sorted((t for t in self.data["todos"] if t["date"] == iso),
                           key=lambda t: (t["done"], t["time"] or "99:99"))
            overdue = sorted((t for t in self.data["todos"] if t["date"] < iso and not t["done"]),
                             key=lambda t: t["date"])
            upcoming = []
            for offset in range(31):
                day = today + dt.timedelta(days=offset)
                for ev in self.data["events"]:
                    if occurs_on(ev, day):
                        upcoming.append({**ev, "date": day.isoformat(), "start": ev["date"]})
            upcoming.sort(key=lambda e: (e["date"], e["time"] or "99:99"))
            exams = [e for e in upcoming if e["kind"] == "시험"]
            dday = ({"title": exams[0]["title"], "date": exams[0]["date"],
                     "days": (dt.date.fromisoformat(exams[0]["date"]) - today).days} if exams else None)
            running = self.data["focus"]["running"]
            focus = None
            if running:
                remaining = int((dt.datetime.fromisoformat(running["end"]) - now).total_seconds())
                focus = {**running, "remaining": max(0, remaining)}
            month_ago = (today - dt.timedelta(days=31)).isoformat()
            return {"today": iso, "weekday": WEEKDAYS[today.weekday()], "todos": [dict(t) for t in todos],
                    "overdue": [dict(t) for t in overdue],
                    "today_events": [e for e in upcoming if e["date"] == iso], "upcoming": upcoming[:60],
                    "events": [dict(e) for e in self.data["events"]],
                    "all_todos": [dict(t) for t in self.data["todos"] if t["date"] >= month_ago],
                    "dday": dday, "focus": focus, "stats": self._stats(today)}

    # ---- 알림 고르기 ----
    def due(self, briefing: str = "") -> list[dict]:
        """지금 보내야 할 알림. 한 번 고른 알림은 다시 안 고른다."""
        with self.lock:
            now = self.now()
            today = now.date()
            fired = self.data["fired"]
            items = []

            def fire(key, at, title, body, who="secretary", late=LATE):
                if at <= now < at + late and key not in fired:
                    fired.append(key)
                    items.append({"title": title, "body": body, "who": who, "reminder": True})

            for ev in self.data["events"]:
                for day in (today, today + dt.timedelta(days=1)):
                    if not occurs_on(ev, day):
                        continue
                    if ev["time"] and ev["remind"] is not None:
                        at = dt.datetime.combine(day, dt.time.fromisoformat(ev["time"])) - dt.timedelta(minutes=ev["remind"])
                        when = "지금" if ev["remind"] == 0 else f"{ev['remind']}분 뒤"
                        fire(f"e:{ev['id']}:{day}", at, f"{ev['kind']} 알림", f"{when} {ev['title']} ({ev['time']})")
                    if ev["kind"] == "시험" and day == today + dt.timedelta(days=1):
                        fire(f"x:{ev['id']}:{day}", dt.datetime.combine(today, dt.time(20, 0)), "내일 시험!",
                             f"{ev['title']} — 마지막으로 훑어보고 일찍 자자", late=dt.timedelta(hours=4))
            for todo in self.data["todos"]:
                if todo["time"] and not todo["done"]:
                    at = dt.datetime.combine(dt.date.fromisoformat(todo["date"]), dt.time.fromisoformat(todo["time"]))
                    fire(f"t:{todo['id']}:{todo['date']}{todo['time']}", at, "할 일 시간이야", todo["text"])

            running = self.data["focus"]["running"]
            if running and now >= dt.datetime.fromisoformat(running["end"]):
                self._log_focus(running, running["minutes"])
                self.data["focus"]["running"] = None
                if running["kind"] == "focus":
                    items.append({"title": f"집중 {running['minutes']}분 끝!", "who": "coach", "reminder": True,
                                  "body": f"{running['task'] + ' — ' if running['task'] else ''}잘했어! 5분 쉬자"})
                else:
                    items.append({"title": "쉬는 시간 끝!", "body": "다시 집중해볼까?", "who": "coach", "reminder": True})

            if briefing and TIME.fullmatch(briefing):
                at = dt.datetime.combine(today, dt.time.fromisoformat(briefing))
                if at <= now < at + dt.timedelta(hours=3) and f"b:{today}" not in fired:
                    fired.append(f"b:{today}")
                    view = self.view()
                    body = f"할 일 {len([t for t in view['todos'] if not t['done']])}개 · 일정 {len(view['today_events'])}개"
                    if view["overdue"]:
                        body += f" · 밀린 일 {len(view['overdue'])}개"
                    if view["dday"]:
                        body += f" · {view['dday']['title']} D-{view['dday']['days']}"
                    items.append({"title": f"좋은 아침! {today.month}/{today.day}({view['weekday']}) 브리핑",
                                  "body": body, "who": "secretary", "reminder": False})

            if items:
                del fired[:-MAX_FIRED]
                self._save()
            return items
