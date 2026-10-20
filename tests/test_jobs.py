import pytest
from office import Material, OfficeError
from office.jobs import Office, merge

def test_scan_to_pdf_job_finishes(make_office):
    office = make_office()
    job_id, job_dir = office.new_job_dir()
    office.submit(job_id, "이 프린트 PDF로", [job_dir / "inputs" / "00.jpg"])
    assert office.run_next() is True
    snap = office.snapshot()
    job = snap["jobs"][0]
    assert job["status"] == "done" and job["title"] == "세포"
    assert job["results"]["pdf"] == f"/files/jobs/{job_id}/note.pdf"
    assert (job_dir / "source.txt").read_text(encoding="utf-8") == "# 세포"
    assert (job_dir / "job.json").exists()
    assert snap["staff"]["designer"]["state"] == "done" and snap["staff"]["manager"]["name"] == "실장"
    assert any(line.startswith("[스캐너]") for line in job["log"])

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
    assert jobs[j2]["status"] == "done"

def test_unexpected_exception_is_caught(make_office):
    def crash(files, say):
        raise ValueError("boom")
    office = make_office(scan=crash)
    j, d = office.new_job_dir(); office.submit(j, "PDF로", [d / "inputs" / "00.jpg"]); office.run_next()
    assert office.snapshot()["jobs"][0]["error"].startswith("예상 못 한 오류")

def test_deploy_publishes_and_sets_url(make_office, tmp_path):
    office = make_office()
    j, _ = office.new_job_dir(); office.submit(j, "운수 좋은 날 문제", []); office.run_next()
    office.submit_deploy(j); office.run_next()
    assert office.snapshot()["jobs"][0]["results"]["deploy_url"] == f"https://ritual-quiz.vercel.app/q/{j}/"
    assert (tmp_path / "ritual-quiz" / "q" / j / "index.html").exists()

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
