import io
import zipfile
from fastapi.testclient import TestClient
from office import llm
from office.notify import Notifier
from office.server import create_app, tick

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
    assert len(s["staff"]) == 16 and {"manager", "analyst", "translator", "coach"} <= set(s["staff"])
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
    assert r.status_code == 200 and "ritual's rab" in r.text and 'src="app.js"' in r.text

def test_cross_site_post_is_rejected(make_office, tmp_path):
    client = TestClient(create_app(make_office()), base_url=BASE)
    r = client.post("/api/command", data={"text": "PDF로"}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and not list((tmp_path / "jobs").iterdir())

def test_foreign_host_is_rejected(make_office):
    r = TestClient(create_app(make_office()), base_url="http://evil.example:8765").get("/api/state")
    assert r.status_code == 403


def client_for(office):
    return TestClient(create_app(office), base_url=BASE)

def upload(name="a.jpg"):
    return [("files", (name, b"x", "application/octet-stream"))]

def test_command_keeps_original_names_and_checks_ref(make_office):
    office = make_office()
    c = client_for(office)
    first = c.post("/api/command", data={"text": "PDF로"}, files=upload("기말 대비.HWP")).json()["job_id"]
    office.run_next()
    assert office.jobs[first].names == ["기말 대비.HWP"] and c.get("/api/state").json()["jobs"][0]["names"] == ["기말 대비.HWP"]
    r = c.post("/api/command", data={"text": "이걸로 문제", "ref": "../../etc"})
    assert r.status_code == 400 and "자료" in r.json()["error"]
    r = c.post("/api/command", data={"text": "이걸로 문제", "ref": first})
    assert r.status_code == 200 and office.jobs[r.json()["job_id"]].ref == first

def test_approve_reject_retry_delete_endpoints(make_office):
    office = make_office()
    c = client_for(office)
    j = c.post("/api/command", data={"text": "PDF로"}, files=upload()).json()["job_id"]
    office.run_next()
    assert c.post(f"/api/jobs/{j}/reject", json={"comment": " "}).status_code == 400
    assert c.post(f"/api/jobs/{j}/reject", json={"comment": "더 쉽게"}).json() == {"ok": True}
    office.run_next()
    assert c.post(f"/api/jobs/{j}/approve", json={"comment": "좋아"}).json() == {"ok": True}
    assert office.jobs[j].status == "done"
    busy = c.post("/api/command", data={"text": "PDF로"}, files=upload()).json()["job_id"]
    assert c.post(f"/api/jobs/{busy}/retry").status_code == 400  # 대기 중이면 다시 못 함
    office.run_next()
    assert c.post(f"/api/jobs/{j}/delete").json() == {"ok": True} and j not in office.jobs
    assert c.post("/api/jobs/nope/approve", json={}).status_code == 400

def test_ceo_office_and_auto_rules(make_office):
    office = make_office()
    c = client_for(office)
    assert c.post("/api/auto", json={"pdf": True}).json()["pdf"] is True
    assert c.post("/api/auto", json={"pdf": 1}).status_code == 400
    j = c.post("/api/command", data={"text": "운수 좋은 날 문제"}).json()["job_id"]
    office.run_next()
    c.post(f"/api/jobs/{j}/approve", json={"comment": "통과"})
    ceo = c.get("/api/ceo").json()
    assert ceo["stats"]["total"] == 1 and ceo["auto"]["pdf"] is True
    assert ceo["history"][0]["job"] == j and ceo["history"][0]["comment"] == "통과" and ceo["history"][0]["title"] == "운수 좋은 날"

def test_planner_endpoints(make_office):
    c = client_for(make_office())
    todo = c.post("/api/todos", json={"text": "영어 단어"}).json()
    assert c.post(f"/api/todos/{todo['id']}", json={"done": True}).json()["done"] is True
    assert c.post("/api/todos", json={"text": ""}).status_code == 400
    ev = c.post("/api/events", json={"title": "수학 학원", "date": "2026-12-01", "time": "15:00", "remind": 10}).json()
    assert ev["kind"] == "일정" and c.post("/api/events", json={"title": "x"}).status_code == 400
    assert c.post(f"/api/events/{ev['id']}/delete").json() == {"ok": True}
    assert c.post("/api/focus", json={"minutes": 25, "task": "과학"}).json()["minutes"] == 25
    s = c.get("/api/state").json()
    assert s["planner"]["focus"]["task"] == "과학" and s["planner"]["todos"][0]["text"] == "영어 단어"
    assert s["version"] and s["ai"] in ("fast", "careful")
    assert c.post("/api/focus/stop").json()["minutes"] == 0
    assert c.post(f"/api/todos/{todo['id']}/delete").json() == {"ok": True}

def test_settings_ai_mode_and_test_alert(make_office, tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "mode", "fast")
    monkeypatch.setattr(llm, "warm", lambda: None)
    ran = []
    office = make_office()
    office.notifier = Notifier(tmp_path / "settings.json", run=lambda cmd, **k: ran.append(cmd),
                               post=lambda url, payload: None, register=lambda: None)
    c = client_for(office)
    s = c.post("/api/settings", json={"ai": "careful", "briefing": "08:00"}).json()
    assert s["settings"]["ai"] == "careful" and s["settings"]["briefing"] == "08:00" and llm.mode == "careful"
    assert c.post("/api/settings", json={"ai": "turbo"}).status_code == 400
    assert c.post("/api/settings/test").json()["errors"] == [] and ran
    assert c.get("/api/settings").json()["history"][0]["title"] == "테스트 알림"
    assert c.get("/api/state").json()["model"] == "qwen3.5:latest"

def test_backup_zip_has_everything(make_office):
    c = client_for(make_office())
    c.post("/api/todos", json={"text": "백업 확인"})
    r = c.get("/api/backup")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert "planner.json" in zipfile.ZipFile(io.BytesIO(r.content)).namelist()

def test_scheduler_tick_sends_due_alarms(make_office):
    office = make_office()
    office.planner.due = lambda briefing="": [{"title": "할 일 시간이야", "body": "단어", "reminder": True}]
    tick(office)
    assert office.notifier.sent == ["할 일 시간이야"]

def test_startup_toggle(make_office, monkeypatch):
    state = {"on": False}
    monkeypatch.setattr("office.startup.is_enabled", lambda path=None: state["on"])
    monkeypatch.setattr("office.startup.set_enabled", lambda on, path=None, run=None: state.update(on=on) or on)
    c = client_for(make_office())
    assert c.get("/api/startup").json() == {"on": False}
    assert c.post("/api/startup", json={"on": True}).json() == {"on": True} and state["on"] is True
    assert c.post("/api/startup", json={"on": "yes"}).status_code == 400


# ---- 편의 기능 · 히스토리 · 초기화 · 실장님 권한 ----
def test_job_buttons_cancel_star_rename_zip(make_office):
    office = make_office()
    c = client_for(office)
    j = c.post("/api/command", data={"text": "PDF로"}, files=upload()).json()["job_id"]
    assert c.post(f"/api/jobs/{j}/cancel").json() == {"ok": True, "state": "cancelled"}
    office.run_next()
    assert office.jobs[j].status == "cancelled"
    assert c.post(f"/api/jobs/{j}/star").json() == {"star": True}
    assert c.post(f"/api/jobs/{j}/rename", json={"title": "새 제목"}).json() == {"ok": True} and office.jobs[j].title == "새 제목"
    z = c.get(f"/api/jobs/{j}/zip")
    assert z.status_code == 200 and z.headers["content-type"] == "application/zip"

def test_history_endpoint_pages_and_filters(make_office):
    office = make_office()
    c = client_for(office)
    for _ in range(3):
        c.post("/api/command", data={"text": "PDF로"}, files=upload())
        office.run_next()
    h = c.get("/api/history", params={"limit": 2}).json()
    assert h["total"] == 3 and len(h["jobs"]) == 2 and h["more"] is True and h["counts"]["review"] == 3
    assert c.get("/api/history", params={"q": "없는말"}).json()["total"] == 0

def test_reset_endpoint(make_office):
    office = make_office()
    c = client_for(office)
    office.planner.add_todo("끝낸 일")
    office.planner.update_todo(office.planner.data["todos"][0]["id"], {"done": True})
    office.planner.add_todo("남은 일")
    assert c.post("/api/reset", json={"what": "todos"}).json() == {"count": 1}
    assert [t["text"] for t in office.planner.data["todos"]] == ["남은 일"]
    assert c.post("/api/reset", json={"what": "staff"}).json() == {"count": 16}
    assert c.post("/api/reset", json={"what": "nope"}).status_code == 400

def test_rab_permissions_endpoint(make_office, tmp_path, monkeypatch):
    office = make_office()
    c = client_for(office)
    p = c.get("/api/permissions").json()
    assert p["read"] is True and p["write"] is True and "Desktop" in p["folders"] or p["folders"] == {}
    extra = tmp_path / "학교 자료"
    extra.mkdir()
    assert "시스템" in c.post("/api/permissions", json={"extra": [str(extra)]}).json()["error"]  # pytest 임시 폴더는 AppData 아래
    from office import tools
    monkeypatch.setattr(tools, "BLOCKED", tools.BLOCKED - {"appdata"})
    p = c.post("/api/permissions", json={"write": False, "extra": [str(extra)]}).json()
    assert p["write"] is False and p["extra"] == [str(extra)] and office.files.allowed(extra)
    assert c.post("/api/permissions", json={"extra": [str(tmp_path / "없는 폴더")]}).status_code == 400
    assert c.post("/api/permissions", json={"read": "yes"}).status_code == 400

def test_memory_endpoints(make_office):
    office = make_office()
    c = client_for(office)
    fact = c.post("/api/memory", json={"text": "대표님은 아침형"}).json()
    assert c.get("/api/memory").json()["facts"][0]["text"] == "대표님은 아침형"
    assert c.post(f"/api/memory/{fact['id']}/delete").json() == {"ok": True} and c.get("/api/memory").json()["facts"] == []
    assert c.post("/api/memory", json={"text": " "}).status_code == 400


def test_media_status_and_shutdown_closes_comfy(make_office, monkeypatch):
    office = make_office()

    class Media:
        closed = False

        def missing(self):
            return ["동영상 모델(Wan2.2 5B)"]

        def up(self):
            return False

        def close(self):
            self.closed = True
    office.media = Media()
    c = client_for(office)
    assert c.get("/api/media").json() == {"missing": ["동영상 모델(Wan2.2 5B)"], "running": False}
    monkeypatch.setattr("office.server.threading.Timer", lambda delay, fn, args: type("T", (), {"start": lambda self: None})())
    assert c.post("/api/shutdown").json() == {"ok": True}
    assert office.media.closed  # 퇴근하면 그림·영상 AI(ComfyUI)도 끈다
