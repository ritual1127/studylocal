import datetime
import json
import pytest
from office import Material, OfficeError
from office.jobs import Office, merge
from office.plan import Plan


def run(office, text, files=(), ref=""):
    job_id, job_dir = office.new_job_dir()
    office.submit(job_id, text, [job_dir / "inputs" / f for f in files], ref=ref)
    office.run_next()
    return office.jobs[job_id]


def routes(**by_text):
    """명령 글자 → Plan. 첨부가 있으면 'files' 키."""
    def route(text, has_files, has_ref=False):
        return by_text["files"] if has_files else by_text[text]
    return route


def test_scan_to_pdf_job_waits_for_approval(make_office):
    office = make_office()
    job_id, job_dir = office.new_job_dir()
    office.submit(job_id, "이 프린트 PDF로", [job_dir / "inputs" / "00.jpg"])
    assert office.run_next() is True
    snap = office.snapshot()
    job = snap["jobs"][0]
    assert job["status"] == "review" and job["title"] == "세포"
    assert job["results"]["pdf"] == f"/files/jobs/{job_id}/note.pdf"
    assert (job_dir / "source.txt").read_text(encoding="utf-8") == "# 세포"
    assert (job_dir / "job.json").exists() and job["seconds"] >= 0
    assert snap["staff"]["designer"]["state"] == "done" and snap["staff"]["manager"]["name"] == "rab"
    assert any(line.startswith("[스캐너]") for line in job["log"])
    assert len(snap["staff"]) == 14

def test_missing_material_asks_back(make_office):
    office = make_office()
    job_id, _ = office.new_job_dir()
    office.submit(job_id, "PDF 만들어줘", [])
    office.run_next()
    job = office.snapshot()["jobs"][0]
    assert job["status"] == "needs_input" and job["reply"].startswith("자료가 없어")

def test_step_error_marks_job_and_worker_survives(make_office):
    def broken_scan(files, say):
        raise OfficeError("JPG·PNG·WEBP·PDF만 읽을 수 있어.")
    office = make_office(scan=broken_scan)
    j1, d1 = office.new_job_dir(); office.submit(j1, "PDF로", [d1 / "inputs" / "00.heic"])
    j2, _ = office.new_job_dir(); office.submit(j2, "운수 좋은 날 문제", [])
    office.run_next(); office.run_next()
    jobs = {j["id"]: j for j in office.snapshot()["jobs"]}
    assert jobs[j1]["status"] == "error" and "JPG" in jobs[j1]["error"]
    assert jobs[j2]["status"] == "review"
    assert office.staff["scanner"]["state"] == "idle"  # 다음 작업이 시작할 때 다시 쉬는 중

def test_unexpected_exception_is_caught(make_office):
    def crash(files, say):
        raise ValueError("boom")
    office = make_office(scan=crash)
    j, d = office.new_job_dir(); office.submit(j, "PDF로", [d / "inputs" / "00.jpg"]); office.run_next()
    assert office.snapshot()["jobs"][0]["error"].startswith("예상 못 한 오류")
    assert office.staff["scanner"]["state"] == "error"

def test_deploy_needs_ceo_approval_then_publishes(make_office, tmp_path):
    office = make_office()
    job = run(office, "운수 좋은 날 문제")
    assert job.status == "review" and office.notifier.sent == ["결재 요청: 운수 좋은 날"]
    with pytest.raises(OfficeError, match="승인"):
        office.submit_deploy(job.id)
    office.approve(job.id, " 좋아 ")
    assert job.status == "done" and job.finished and job.approvals[-1]["action"] == "approve"
    assert job.approvals[-1]["by"] == "대표" and job.approvals[-1]["comment"] == "좋아"
    with pytest.raises(OfficeError, match="결재 대기"):
        office.approve(job.id)
    office.submit_deploy(job.id); office.run_next()
    assert job.results["deploy_url"] == f"https://ritual-quiz.vercel.app/q/{job.id}/"
    assert (tmp_path / "ritual-quiz" / "q" / job.id / "index.html").exists()

def test_deploy_requires_quiz(make_office):
    office = make_office()
    j, d = office.new_job_dir(); office.submit(j, "PDF로", [d / "inputs" / "00.jpg"]); office.run_next()
    with pytest.raises(OfficeError, match="문제 웹"):
        office.submit_deploy(j)

def test_history_survives_restart(make_office, tmp_path):
    office = make_office()
    j, d = office.new_job_dir(); office.submit(j, "PDF로", [d / "inputs" / "00.jpg"]); office.run_next()
    fresh = Office(tmp_path)
    fresh.load_history()
    assert fresh.snapshot()["jobs"][0]["id"] == j

def test_merge_two_sources():
    m = merge([Material(title="프린트", markdown="A", sources=["1.jpg"]),
               Material(title="운수 좋은 날", markdown="B", sources=["u"], original="원문")], title="")
    assert (m.title, m.markdown, m.sources, m.original) == ("프린트", "A\n\n---\n\nB", ["1.jpg", "u"], "원문")


# ---- 2단계: 제목, 새 직원, 이전 자료 ----
def test_title_prefers_material_heading_over_router_title(make_office):
    route = routes(files=Plan(steps=["scan", "pdf"], title="프린트 기반 학습 자료"))
    office = make_office(route=route, scan=lambda files, say: Material(title="세포의 구조", markdown="# 세포의 구조"))
    assert run(office, "PDF로", ["00.jpg"]).title == "세포의 구조"
    office = make_office(route=route, scan=lambda files, say: Material(title="", markdown="본문"))
    assert run(office, "PDF로", ["00.jpg"]).title == "프린트 기반 학습 자료"

def test_new_staff_make_their_outputs(make_office):
    seen = {}

    def cards(material, count, job_dir, say, feedback=""):
        seen["cards"] = (material.title, count)
        (job_dir / "cards").mkdir()
        (job_dir / "cards" / "cards.csv").write_text("a,b", encoding="utf-8")
        (job_dir / "cards" / "index.html").write_text("c", encoding="utf-8")
        return job_dir / "cards" / "index.html"

    def translate(material, target, job_dir, say, feedback=""):
        seen["target"] = target
        (job_dir / "translation").mkdir()
        (job_dir / "translation" / "index.html").write_text("t", encoding="utf-8")
        return job_dir / "translation" / "index.html"
    plan = Plan(steps=["research", "analysis", "cards", "mindmap", "translate", "answer"], topic="광합성",
                question="광합성이 뭐야?", card_count=7, target_lang="영어", title="광합성")
    office = make_office(route=routes(광합성=plan), cards=cards, translate=translate)
    job = run(office, "광합성")
    assert seen == {"cards": ("광합성", 7), "target": "영어"}
    assert set(job.results) == {"text", "analysis", "cards", "csv", "mindmap", "translation", "answer"}
    assert job.answer == "답: 광합성이 뭐야?" and job.status == "review"
    staff = office.snapshot()["staff"]
    assert all(staff[r]["state"] == "done" for r in ("researcher", "analyst", "cards", "mapper", "translator", "tutor"))
    saved = json.loads((office.jobs_dir / job.id / "material.json").read_text(encoding="utf-8"))
    assert saved["title"] == "광합성" and saved["sources"] == ["wiki"]

def test_selected_material_is_reused(make_office):
    seen = {"has_ref": []}

    def route(text, has_files, has_ref=False):
        seen["has_ref"].append(has_ref)
        return Plan(steps=["scan", "pdf"]) if has_files else Plan(steps=["quiz"], question_count=4)

    def quiz(material, count, job_dir, say, feedback=""):
        seen["quiz"] = (material.markdown, count)
        (job_dir / "quiz").mkdir()
        (job_dir / "quiz" / "index.html").write_text("q", encoding="utf-8")
        return job_dir / "quiz" / "index.html"
    office = make_office(route=route, quiz=quiz)
    first = run(office, "PDF로", ["00.jpg"])
    second = run(office, "이걸로 문제", ref=first.id)
    assert seen["has_ref"] == [False, True] and seen["quiz"] == ("# 세포", 4) and second.title == "세포"
    assert any("다시 꺼냈어" in line for line in second.log)

def test_use_last_takes_latest_material_or_asks(make_office):
    office = make_office(route=routes(files=Plan(steps=["scan", "pdf"]), 아까=Plan(steps=["mindmap"], use_last=True)))
    asked = run(office, "아까")
    assert asked.status == "needs_input" and "이전 자료" in asked.reply
    run(office, "PDF로", ["00.jpg"])
    job = run(office, "아까")
    assert job.status == "review" and "mindmap" in job.results and job.title == "세포"

def test_schedule_plan_and_focus_go_to_planner(make_office):
    seen = {}

    def schedule(text, today):
        seen["schedule_text"] = text
        exam = (today + datetime.timedelta(days=10)).isoformat()
        return {"events": [{"title": "기말고사", "date": exam, "time": "", "kind": "시험", "remind": None, "repeat": "none"}],
                "todos": [{"text": "영어 단어", "date": today.isoformat(), "time": ""}], "reply": "넣었어"}

    def plan(text, today, exams, material):
        seen["exams"] = [e["title"] for e in exams]
        return {"todos": [{"date": today.isoformat(), "text": "1단원 복습"}], "reply": "화이팅"}
    route = routes(files=Plan(steps=["scan", "schedule", "plan", "focus"], focus_minutes=50, title="기말 준비"))
    office = make_office(route=route, schedule=schedule, plan=plan)
    job = run(office, "기말 등록하고 계획 짜고 50분 공부모드", ["00.jpg"])
    view = office.planner.view()
    assert job.status == "done" and not job.approvals and seen["exams"] == ["기말고사"]
    assert "기말 등록하고" in seen["schedule_text"] and "# 세포" in seen["schedule_text"]  # 사진 속 일정도 읽는다
    assert [t["text"] for t in view["todos"]] == ["영어 단어", "1단원 복습"]
    assert view["dday"]["title"] == "기말고사" and view["focus"]["minutes"] == 50
    assert office.notifier.sent == []  # 결과물 없는 작업은 알림 안 보냄


# ---- 대표 결재 ----
def test_reject_reworks_with_ceo_feedback(make_office):
    seen = []

    def pdf(material, job_dir, say, feedback=""):
        seen.append((material.markdown, feedback))
        (job_dir / "note.pdf").write_bytes(b"%PDF")
        return job_dir / "note.pdf"
    office = make_office(pdf=pdf)
    job = run(office, "PDF로", ["00.jpg"])
    with pytest.raises(OfficeError, match="적어"):
        office.reject(job.id, "  ")
    office.reject(job.id, "표를 더 넣어줘")
    assert job.status == "revising" and job.revision == 1
    office.run_next()
    assert seen == [("# 세포", ""), ("# 세포", "표를 더 넣어줘")]
    assert job.status == "review" and [a["action"] for a in job.approvals] == ["reject"]
    assert office.notifier.sent == ["결재 요청: 세포", "결재 요청: 세포"]

def test_failed_rework_goes_back_to_review_with_error(make_office):
    def pdf(material, job_dir, say, feedback=""):
        if feedback:
            raise OfficeError("PDF 만들기 실패: 테스트")
        (job_dir / "note.pdf").write_bytes(b"%PDF")
        return job_dir / "note.pdf"
    office = make_office(pdf=pdf)
    job = run(office, "PDF로", ["00.jpg"])
    office.reject(job.id, "더 예쁘게"); office.run_next()
    assert job.status == "review" and "PDF 만들기 실패" in job.error
    assert office.notifier.sent[-1] == "수정 실패: 세포"
    office.approve(job.id)
    assert job.status == "done" and job.error is None

def test_auto_approve_rules(make_office, tmp_path):
    office = make_office(route=routes(files=Plan(steps=["scan", "pdf"]), 질문=Plan(steps=["answer"])))
    job = run(office, "질문")
    assert job.status == "done" and job.approvals[0]["action"] == "auto" and office.notifier.sent == ["작업 완료: 질문"]
    assert office.set_auto({"pdf": True})["pdf"] is True
    assert run(office, "PDF로", ["00.jpg"]).status == "done"
    assert Office(tmp_path).auto["pdf"] is True  # 다시 켜도 그대로
    with pytest.raises(OfficeError):
        office.set_auto({"pdf": "yes"})
    with pytest.raises(OfficeError):
        office.set_auto({"deploy": True})

def test_job_done_switch_mutes_done_and_failure_but_not_approval(make_office):
    office = make_office(route=routes(files=Plan(steps=["scan", "pdf"]), 질문=Plan(steps=["answer"])))
    office.notifier.settings["job_done"] = False
    run(office, "질문"); run(office, "PDF로", ["00.jpg"])
    assert office.notifier.sent == ["결재 요청: 세포"]

def test_restart_keeps_pending_reviews_beyond_recent_window(make_office, tmp_path, monkeypatch):
    office = make_office()
    run(office, "안녕")                                  # 되물음 (최근 창 밖이면 안 불러옴)
    old = run(office, "PDF로", ["00.jpg"])                # 결재 대기
    crashed = run(office, "PDF로", ["00.jpg"])
    crashed.status = "revising"; office._save(crashed)   # 고치다가 꺼짐
    monkeypatch.setattr("office.jobs.MAX_JOBS", 0)
    fresh = Office(tmp_path)
    fresh.load_history()
    jobs = {j["id"]: j for j in fresh.snapshot()["jobs"]}
    assert set(jobs) == {old.id, crashed.id}
    assert jobs[crashed.id]["status"] == "review" and "중단" in jobs[crashed.id]["error"]

def test_retry_error_job_and_delete(make_office):
    calls = []

    def scan(files, say):
        calls.append(1)
        if len(calls) == 1:
            raise OfficeError("사진이 흐려")
        return Material(title="세포", markdown="# 세포")
    office = make_office(scan=scan)
    job = run(office, "PDF로", ["00.jpg"])
    assert job.status == "error" and office.notifier.sent == ["작업 실패: PDF로"]
    office.retry(job.id); office.run_next()
    assert job.status == "review" and job.error is None and len(calls) == 2
    busy, _ = office.new_job_dir(); office.submit(busy, "PDF로", [])
    with pytest.raises(OfficeError, match="일하는 중"):
        office.retry(busy)  # 대기·진행 중인 작업은 다시 못 한다
    with pytest.raises(OfficeError, match="일하는 중"):
        office.delete(busy)
    office.delete(job.id)
    assert job.id not in office.jobs and not (office.jobs_dir / job.id).exists()
    with pytest.raises(OfficeError):
        office.delete("nope")

def test_deleted_job_left_in_queue_is_skipped(make_office):
    office = make_office()
    job = run(office, "운수 좋은 날 문제"); office.approve(job.id)
    office.submit_deploy(job.id)
    office.delete(job.id)
    assert office.run_next() is True and office.snapshot()["jobs"] == []

def test_stats_for_ceo_office(make_office):
    office = make_office(route=routes(files=Plan(steps=["scan", "pdf"]), 질문=Plan(steps=["answer"])))
    a = run(office, "PDF로", ["00.jpg"]); office.approve(a.id)
    b = run(office, "PDF로", ["00.jpg"]); office.reject(b.id, "다시"); office.run_next()
    run(office, "질문")
    s = office.stats()
    assert s["pending"] == 1 and s["today_done"] == 2 and s["approval_rate"] == 50 and s["auto_approved"] == 1
    assert s["staff"]["designer"] == 2 and s["staff"]["scanner"] == 2 and s["staff"]["tutor"] == 1
    assert s["staff"]["manager"] == 3 and s["study_week"] == 0

def test_jobs_get_running_numbers_that_survive_restart(make_office, tmp_path):
    office = make_office()
    a = run(office, "안녕")
    b = run(office, "PDF로", ["00.jpg"])
    assert (a.no, b.no) == (1, 2)
    again = Office(tmp_path)
    j, _ = again.new_job_dir()
    again.submit(j, "x", [])
    assert again.jobs[j].no == 3
