import datetime
import json

import pytest

from office.agent import resolve_time


def call(_tool, **args):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": _tool, "arguments": args}}]}


def say(text):
    return {"role": "assistant", "content": text}


class Script:
    """가짜 모델: 정해진 답을 차례로 내고, 받은 대화를 기록한다."""
    def __init__(self, *turns, hook=None):
        self.turns, self.seen, self.hook = list(turns), [], hook

    def __call__(self, messages, tools):
        self.seen.append([dict(m) for m in messages])
        self.tool_names = [t["function"]["name"] for t in tools]
        if self.hook:
            self.hook(len(self.seen))
        return self.turns.pop(0) if self.turns else say("대표님, 끝냈습니다.")

    def results(self, name):
        last = self.seen[-1]
        return [json.loads(m["content"]) for m in last if m.get("role") == "tool" and m.get("tool_name") == name]


def run(office, text, files=()):
    job_id, job_dir = office.new_job_dir()
    paths = []
    for name in files:
        (job_dir / "inputs" / name).write_bytes(b"x")
        paths.append(job_dir / "inputs" / name)
    office.submit(job_id, text, paths, names=list(files))
    office.run_next()
    return office.jobs[job_id]


def test_goodnight_goes_to_phone(make_agent_office):
    script = Script(call("notify", to="phone", message="굿나잇"), say("대표님, 폰으로 '굿나잇' 보냈습니다."))
    office = make_agent_office(script)
    job = run(office, "내 폰으로 굿나잇이라고 보내")
    assert office.notifier.to == [("phone", "rab", "굿나잇")]
    assert job.status == "done" and job.reply == "대표님, 폰으로 '굿나잇' 보냈습니다." and job.trace
    assert {"notify", "find_files", "bring_file", "do_work", "status"} <= set(script.tool_names)
    assert script.seen[0][0]["role"] == "system" and "ritual's rab" in script.seen[0][0]["content"]


def test_find_then_bring_file_into_office(make_agent_office, agent_home):
    script = Script(call("find_files", query="수학 프린트"), call("bring_file", path=str(agent_home / "Desktop" / "수학_프린트.pdf")),
                    say("대표님, 가져왔습니다."))
    office = make_agent_office(script)
    job = run(office, "바탕화면에서 수학 프린트 찾아서 가져와")
    found = [m for m in script.seen[1] if m.get("role") == "tool"][0]
    assert "수학_프린트.pdf" in found["content"]
    assert job.names == ["수학_프린트.pdf"] and (office.jobs_dir / job.id / "inputs" / "수학_프린트.pdf").exists()
    assert job.results["files"] == [{"name": "수학_프린트.pdf", "url": f"/files/jobs/{job.id}/inputs/수학_프린트.pdf"}]


def test_do_work_runs_staff_on_attached_file(make_agent_office):
    script = Script(call("do_work", outputs=["pdf"]), say("대표님, 노트를 만들어 결재 올렸습니다."))
    office = make_agent_office(script)
    job = run(office, "이 프린트 PDF로", ["수업.jpg"])
    assert job.status == "review" and "pdf" in job.results and job.title == "세포"
    assert script.results("do_work")[0]["status"] == "결재 대기"


def test_open_write_copy_and_folder_stay_inside(make_agent_office, agent_home):
    script = Script(call("open_thing", target="https://ritual.example"), call("open_thing", target="바탕화면"),
                    call("write_file", name="메모.txt", content="내일 준비물: 자"),
                    call("copy_file", path=str(agent_home / "Desktop" / "수학_프린트.pdf"), to_folder="다운로드"),
                    call("make_folder", path="문서/기말 자료"), say("대표님, 다 했습니다."))
    office = make_agent_office(script)
    run(office, "여러 가지 해줘")
    assert office.opened == ["https://ritual.example", str(agent_home / "Desktop")]
    assert (agent_home / "Documents" / "ritual's rab" / "메모.txt").read_text(encoding="utf-8") == "내일 준비물: 자"
    assert (agent_home / "Downloads" / "수학_프린트.pdf").exists() and (agent_home / "Documents" / "기말 자료").is_dir()


def test_tool_errors_go_back_to_the_model(make_agent_office, agent_home):
    script = Script(call("no_such_tool"), call("read_file", path="C:/Windows/win.ini"), say("대표님, 그건 못 합니다."))
    office = make_agent_office(script)
    job = run(office, "이상한 거 해줘")
    errors = [json.loads(m["content"]) for m in script.seen[-1] if m.get("role") == "tool"]
    assert "없어요" in errors[0]["error"] and "폴더 밖" in errors[1]["error"] and job.status == "done"


def test_turn_limit_stops_the_loop(make_agent_office):
    script = Script(*[call("status", what="today") for _ in range(20)])
    office = make_agent_office(script)
    job = run(office, "계속 확인해")
    assert len(script.seen) == 8 and "멈췄습니다" in job.reply


def test_status_and_planner_tools(make_agent_office):
    script = Script(call("add_schedule", title="기말고사", date="2026-11-20", kind="시험"),
                    call("remind", message="물 마시기", minutes=10), call("todo_done", text="단어 외우기"),
                    call("focus", action="start", minutes=50, task="수학"), call("status", what="today"), say("대표님, 정리했습니다."))
    office = make_agent_office(script)
    office.planner.add_todo("영어 단어 외우기")
    run(office, "정리해줘")
    view = office.planner.view()
    assert any(e["title"] == "기말고사" for e in view["events"]) and view["focus"]["minutes"] == 50
    assert [t["done"] for t in office.planner.data["todos"] if t["text"] == "영어 단어 외우기"] == [True]
    assert any(t["text"] == "물 마시기" and t["time"] for t in office.planner.data["todos"])
    today = script.results("status")[0]
    assert today["focus"]["task"] == "수학" and "할 일" in json.dumps(today, ensure_ascii=False)


def test_job_actions_on_office_work(make_agent_office):
    office = make_agent_office(Script(call("do_work", outputs=["pdf"]), say("올렸습니다.")))
    first = run(office, "PDF로", ["수업.jpg"])
    office.agent.llm = Script(call("job_action", action="approve", job="latest", comment="좋아"), say("승인했습니다."))
    run(office, "방금 거 승인해")
    assert first.status == "done" and first.approvals[-1]["comment"] == "좋아"


def test_cancel_stops_at_next_step(make_agent_office):
    holder = {}
    office = make_agent_office(Script(call("status", what="today"), call("status", what="jobs"), say("끝"),
                                      hook=lambda n: n == 2 and office.cancel(holder["id"])))
    job_id, _ = office.new_job_dir()
    holder["id"] = job_id
    office.submit(job_id, "확인해", [])
    office.run_next()
    job = office.jobs[job_id]
    assert job.status == "cancelled" and office.staff["manager"]["state"] == "idle"


def test_mention_keeps_rab_inside_that_team(make_agent_office):
    script = Script(call("do_work", outputs=["pdf", "quiz"]), say("출제위원에게 맡겼습니다."))
    office = make_agent_office(script)
    job = run(office, "@출제위원 이 프린트로 문제 내줘", ["수업.jpg"])
    assert job.assignee == "examiner" and "quiz" in job.results and "pdf" not in job.results
    assert "출제위원" in script.seen[0][0]["content"]


def test_reminder_time_rules():
    now = datetime.datetime(2026, 10, 21, 20, 3, 40)
    assert resolve_time(now, minutes=10) == datetime.datetime(2026, 10, 21, 20, 14)
    assert resolve_time(now, time="09:30") == datetime.datetime(2026, 10, 21, 21, 30)  # 저녁에 "9시 반" = 오늘 밤
    assert resolve_time(now, time="07:00") == datetime.datetime(2026, 10, 22, 7, 0)
    assert resolve_time(datetime.datetime(2026, 10, 21, 23, 55), minutes=10) == datetime.datetime(2026, 10, 22, 0, 5)
    with pytest.raises(ValueError):
        resolve_time(now)


def test_open_refuses_programs_and_scripts(make_agent_office, agent_home):
    for name in ("setup.exe", "run.bat", "x.ps1", "바로가기.lnk"):
        (agent_home / "Downloads" / name).write_bytes(b"x")
    script = Script(*[call("open_thing", target=f"다운로드/{n}") for n in ("setup.exe", "run.bat", "x.ps1", "바로가기.lnk")],
                    say("못 엽니다."))
    office = make_agent_office(script)
    run(office, "다운로드 설치 파일 열어줘")
    errors = [json.loads(m["content"]).get("error", "") for m in script.seen[-1] if m.get("role") == "tool"]
    assert office.opened == [] and len(errors) == 4 and all("직접" in e for e in errors)


# ---- 기억 · 이어지는 대화 ----
def test_remembered_facts_and_recent_dialogue_reach_the_next_command(make_agent_office):
    script = Script(call("remember", text="대표님은 고2, 수학 학원은 화요일"), say("기억해 둘게요."), say("화요일이에요."))
    office = make_agent_office(script)
    run(office, "나 고2고 수학 학원은 화요일이야, 기억해")
    assert [f["text"] for f in office.memory.facts()] == ["대표님은 고2, 수학 학원은 화요일"]
    run(office, "학원 무슨 요일이라 했지?")
    second = script.seen[-1]
    assert "수학 학원은 화요일" in second[0]["content"]  # 기억이 대화 맨 앞에
    roles = [m["role"] for m in second[:4]]
    assert roles == ["system", "user", "assistant", "user"] and second[1]["content"] == "나 고2고 수학 학원은 화요일이야, 기억해"
    assert second[2]["content"] == "기억해 둘게요." and second[3]["content"] == "학원 무슨 요일이라 했지?"


def test_forget_tool(make_agent_office):
    script = Script(call("forget", text="학원"), say("잊었어요."))
    office = make_agent_office(script)
    office.memory.add("수학 학원은 화요일")
    office.memory.add("좋아하는 과목은 과학")
    run(office, "학원 얘기는 잊어")
    assert [f["text"] for f in office.memory.facts()] == ["좋아하는 과목은 과학"]
    assert script.results("forget")[0]["forgot"] == ["수학 학원은 화요일"]
