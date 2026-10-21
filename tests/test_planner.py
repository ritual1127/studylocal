import datetime
import pytest
from office import OfficeError
from office.planner import Planner


class Clock:
    def __init__(self, text):
        self.t = datetime.datetime.fromisoformat(text)

    def __call__(self):
        return self.t

    def set(self, text):
        self.t = datetime.datetime.fromisoformat(text)


def make(tmp_path, t="2026-10-21 09:00"):
    clock = Clock(t)
    return Planner(tmp_path / "planner.json", now=clock), clock


def titles(items):
    return [i["title"] + " " + i["body"] for i in items]


def test_todo_add_check_and_persist(tmp_path):
    p, clock = make(tmp_path)
    todo = p.add_todo("영어 단어 30개")
    assert todo["date"] == "2026-10-21" and todo["done"] is False
    p.update_todo(todo["id"], {"done": True})
    again = Planner(tmp_path / "planner.json", now=clock)
    assert again.view()["todos"][0]["done"] is True


def test_overdue_then_move_to_today(tmp_path):
    p, _ = make(tmp_path)
    old = p.add_todo("수학 숙제", date="2026-10-20")
    assert [t["text"] for t in p.view()["overdue"]] == ["수학 숙제"]
    p.update_todo(old["id"], {"date": "2026-10-21"})
    v = p.view()
    assert v["overdue"] == [] and v["todos"][0]["text"] == "수학 숙제"


def test_bad_input_rejected(tmp_path):
    p, _ = make(tmp_path)
    with pytest.raises(OfficeError):
        p.add_todo("   ")
    with pytest.raises(OfficeError):
        p.add_todo("a", time="25:00")
    with pytest.raises(OfficeError):
        p.add_event("시험", "2026-13-01")
    with pytest.raises(OfficeError):
        p.add_event("시험", "2026-10-30", kind="파티")
    with pytest.raises(OfficeError, match="그런 할 일이 없어"):
        p.update_todo("nope", {"done": True})


def test_event_reminder_fires_once_in_window(tmp_path):
    p, clock = make(tmp_path)
    p.add_event("수학 학원", "2026-10-21", "15:00", remind=10)
    clock.set("2026-10-21 14:49")
    assert p.due() == []
    clock.set("2026-10-21 14:50:20")
    assert any("수학 학원" in t for t in titles(p.due()))
    clock.set("2026-10-21 14:51")
    assert p.due() == []
    assert Planner(tmp_path / "planner.json", now=clock).due() == []


def test_reminder_missed_by_more_than_10_minutes_is_skipped(tmp_path):
    p, clock = make(tmp_path)
    p.add_event("상담", "2026-10-21", "10:00", remind=0)
    clock.set("2026-10-21 10:11")
    assert p.due() == []


def test_weekly_repeat_and_exam_dday(tmp_path):
    p, clock = make(tmp_path)
    p.add_event("영어 학원", "2026-10-14", "18:00", remind=0, repeat="weekly")
    p.add_event("수학 시험", "2026-10-25", kind="시험")
    v = p.view()
    assert v["dday"] == {"title": "수학 시험", "date": "2026-10-25", "days": 4}
    assert [e["title"] for e in v["today_events"]] == ["영어 학원"]
    clock.set("2026-10-21 18:00:05")
    assert any("영어 학원" in t for t in titles(p.due()))
    clock.set("2026-10-24 20:00:30")
    assert any("수학 시험" in t for t in titles(p.due()))


def test_focus_session_end_logs_and_reports(tmp_path):
    p, clock = make(tmp_path)
    p.start_focus(25, "과학 정리")
    assert p.view()["focus"]["remaining"] == 25 * 60
    clock.set("2026-10-21 09:25:01")
    due = p.due()
    assert due and due[0]["who"] == "coach" and "집중" in due[0]["title"]
    v = p.view()
    assert v["focus"] is None and v["stats"]["today"] == 25 and v["stats"]["streak"] == 1


def test_stop_focus_logs_elapsed_minutes(tmp_path):
    p, clock = make(tmp_path)
    p.start_focus(50)
    clock.set("2026-10-21 09:10:30")
    assert p.stop_focus() == 10
    assert p.view()["stats"]["today"] == 10 and p.due() == []


def test_morning_briefing_once(tmp_path):
    p, clock = make(tmp_path, "2026-10-21 07:00")
    p.add_todo("단어 외우기")
    clock.set("2026-10-21 07:29")
    assert p.due(briefing="07:30") == []
    clock.set("2026-10-21 07:31")
    assert "할 일 1개" in titles(p.due(briefing="07:30"))[0]
    clock.set("2026-10-21 07:40")
    assert p.due(briefing="07:30") == []


def test_timed_todo_reminds_unless_done(tmp_path):
    p, clock = make(tmp_path)
    a = p.add_todo("단어 시험 공부", time="19:00")
    b = p.add_todo("일기", time="19:00")
    p.update_todo(b["id"], {"done": True})
    clock.set("2026-10-21 19:00:10")
    assert titles(p.due()) == ["할 일 시간이야 단어 시험 공부"]
    assert a["id"]


def test_starting_focus_again_keeps_the_running_minutes(tmp_path):
    p, clock = make(tmp_path)
    p.start_focus(50, "수학")
    clock.set("2026-10-21 09:20")
    p.start_focus(25, "영어")
    v = p.view()
    assert v["stats"]["today"] == 20 and v["focus"]["task"] == "영어"
