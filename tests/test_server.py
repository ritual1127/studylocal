from fastapi.testclient import TestClient
from office.server import create_app

BASE = "http://127.0.0.1:8765"

def test_command_saves_upload_inside_job(make_office, tmp_path):
    client = TestClient(create_app(make_office()), base_url=BASE)
    r = client.post("/api/command", data={"text": "PDF로"}, files=[("files", ("../../evil.JPG", b"\xff\xd8", "image/jpeg"))])
    job_id = r.json()["job_id"]
    assert (tmp_path / "jobs" / job_id / "inputs" / "00.jpg").read_bytes() == b"\xff\xd8"
    assert not list(tmp_path.rglob("evil*"))

def test_empty_command_rejected(make_office):
    r = TestClient(create_app(make_office()), base_url=BASE).post("/api/command", data={"text": "  "})
    assert r.status_code == 400 and r.json()["error"] == "명령을 입력해줘."

def test_state_lists_staff_and_jobs(make_office):
    client = TestClient(create_app(make_office()), base_url=BASE)
    client.post("/api/command", data={"text": "운수 좋은 날 문제"})
    s = client.get("/api/state").json()
    assert set(s["staff"]) == {"manager", "scanner", "librarian", "designer", "examiner", "deployer"}
    assert s["jobs"][0]["status"] == "queued" and isinstance(s["ollama"], bool) and s["model"]

def test_deploy_unknown_job_is_400(make_office):
    r = TestClient(create_app(make_office()), base_url=BASE).post("/api/jobs/nope/deploy")
    assert r.status_code == 400 and r.json()["error"] == "그런 작업이 없어."

def test_output_files_are_served(make_office, tmp_path):
    client = TestClient(create_app(make_office()), base_url=BASE)
    (tmp_path / "jobs" / "x").mkdir(parents=True)
    (tmp_path / "jobs" / "x" / "note.pdf").write_bytes(b"%PDF")
    assert client.get("/files/jobs/x/note.pdf").content == b"%PDF"

def test_index_served(make_office):
    r = TestClient(create_app(make_office()), base_url=BASE).get("/")
    assert r.status_code == 200 and "공부 사무실" in r.text and 'src="app.js"' in r.text

def test_cross_site_post_is_rejected(make_office, tmp_path):
    client = TestClient(create_app(make_office()), base_url=BASE)
    r = client.post("/api/command", data={"text": "PDF로"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and not list((tmp_path / "jobs").iterdir())

def test_foreign_host_is_rejected(make_office):
    r = TestClient(create_app(make_office()), base_url="http://evil.example:8765").get("/api/state")
    assert r.status_code == 403
