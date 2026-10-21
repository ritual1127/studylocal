import json
import pytest
from fastapi.testclient import TestClient
from office import OfficeError
from office.remote import Remote, find_tunnel_url
from office.server import create_app, create_remote_app

PHONE = "http://192.168.0.10:8766"
LOCAL = "http://127.0.0.1:8765"


class Starter:
    """서버·터널을 진짜로 띄우지 않고 몇 번 켜고 껐는지만 센다."""
    def __init__(self):
        self.calls = []

    def server(self, host):
        self.calls.append(("server", host))
        return lambda: self.calls.append(("server-stop", host))

    def tunnel(self, on_url):
        self.calls.append(("tunnel",))
        on_url("https://happy-cat-12.trycloudflare.com")
        return lambda: self.calls.append(("tunnel-stop",))


def make_remote(tmp_path, notify=None):
    s = Starter()
    r = Remote(tmp_path / "remote.json", start_server=s.server, start_tunnel=s.tunnel, notify=notify or (lambda t, b: None),
               lan=lambda: ["192.168.0.10"])
    return r, s


def test_modes_start_and_stop_the_right_things(tmp_path):
    r, s = make_remote(tmp_path)
    assert r.status()["mode"] == "off" and not r.check(r.token)
    r.update({"mode": "lan"})
    assert s.calls == [("server", "0.0.0.0")] and r.check(r.token)
    assert r.status()["link"] == f"http://192.168.0.10:8766/m?k={r.token}"
    r.update({"mode": "tunnel"})
    assert s.calls[1:] == [("server-stop", "0.0.0.0"), ("server", "127.0.0.1"), ("tunnel",)]
    assert r.status()["link"] == f"https://happy-cat-12.trycloudflare.com/m?k={r.token}"
    r.update({"mode": "off"})
    assert ("tunnel-stop",) in s.calls and s.calls[-1] == ("server-stop", "127.0.0.1")
    with pytest.raises(OfficeError):
        r.update({"mode": "everywhere"})


def test_new_token_kills_old_links_and_persists(tmp_path):
    r, _ = make_remote(tmp_path)
    r.update({"mode": "lan"})
    old = r.token
    r.update({"new_token": True})
    assert not r.check(old) and r.check(r.token) and len(r.token) >= 32
    again, _ = make_remote(tmp_path)
    assert again.token == r.token and again.mode == "lan"


def test_tunnel_address_goes_to_phone(tmp_path):
    sent = []
    r, _ = make_remote(tmp_path, notify=lambda title, body: sent.append((title, body)))
    r.update({"mode": "tunnel"})
    assert sent and "trycloudflare.com/m?k=" in sent[0][1]


def test_find_tunnel_url_in_cloudflared_log():
    line = "2026-10-21T10:00:00Z INF |  https://quiet-river-a1b2.trycloudflare.com                                 |"
    assert find_tunnel_url(line) == "https://quiet-river-a1b2.trycloudflare.com"
    assert find_tunnel_url("INF Requesting new quick Tunnel on trycloudflare.com...") is None


# ---- 폰 서버 ----
@pytest.fixture
def phone(make_office, tmp_path):
    office = make_office()
    remote, _ = make_remote(tmp_path)
    remote.update({"mode": "lan"})
    return office, remote, TestClient(create_remote_app(office, remote), base_url=PHONE, follow_redirects=False)


def test_phone_needs_token_then_cookie(phone):
    office, remote, c = phone
    assert c.get("/m").status_code == 401
    assert c.get(f"/m?k=wrong").status_code == 401
    r = c.get(f"/m?k={remote.token}")
    assert r.status_code in (302, 307) and r.headers["location"] == "/m"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert c.get("/m").status_code == 200 and "공부 사무실" in c.get("/m").text
    remote.update({"new_token": True})
    assert c.get("/m").status_code == 401  # 토큰을 바꾸면 옛 쿠키는 끝


def login(c, remote):
    c.get(f"/m?k={remote.token}")
    return {"X-Ritual": "1"}


def test_phone_command_state_files_and_approval(phone):
    office, remote, c = phone
    hdr = login(c, remote)
    assert c.post("/api/m/command", data={"text": "PDF로"}, files=[("files", ("수업.jpg", b"x", "image/jpeg"))]).status_code == 403
    job_id = c.post("/api/m/command", data={"text": "PDF로"}, files=[("files", ("수업.jpg", b"x", "image/jpeg"))],
                    headers=hdr).json()["job_id"]
    office.run_next()
    s = c.get("/api/m/state").json()
    job = s["jobs"][0]
    assert job["id"] == job_id and job["status"] == "review" and job["names"] == ["수업.jpg"] and "log" not in job
    assert c.get(job["results"]["pdf"]).content.startswith(b"%PDF")
    assert c.post(f"/api/m/jobs/{job_id}/approve", json={"comment": "폰에서 승인"}, headers=hdr).json() == {"ok": True}
    assert office.jobs[job_id].status == "done" and s["pending"] == 1


def test_phone_cannot_reach_pc_only_things(phone, tmp_path):
    office, remote, c = phone
    login(c, remote)
    (tmp_path / "settings.json").write_text(json.dumps({"topic": "secret"}), encoding="utf-8")
    assert c.get("/files/settings.json").status_code == 404
    for path in ("/api/shutdown", "/api/backup", "/api/settings", "/api/state", "/"):
        assert c.get(path).status_code in (404, 405, 307) and "secret" not in c.get(path).text


def test_phone_checks_todos(phone):
    office, remote, c = phone
    hdr = login(c, remote)
    todo = office.planner.add_todo("단어 외우기")
    assert c.post(f"/api/m/todos/{todo['id']}", json={"done": True}, headers=hdr).json()["done"] is True
    assert c.get("/api/m/state").json()["planner"]["todos"][0]["done"] is True


# ---- PC 설정 화면에서 ----
def test_pc_settings_turn_phone_access_on_and_show_qr(make_office, tmp_path):
    office = make_office()
    remote, _ = make_remote(tmp_path)
    c = TestClient(create_app(office, remote=remote), base_url=LOCAL)
    assert c.get("/api/remote").json()["mode"] == "off"
    status = c.post("/api/remote", json={"mode": "lan"}).json()
    assert status["mode"] == "lan" and status["link"].endswith(remote.token)
    qr = c.get("/api/remote/qr")
    assert qr.status_code == 200 and qr.headers["content-type"].startswith("image/svg+xml")
    assert c.post("/api/remote", json={"mode": "moon"}).status_code == 400


def test_shutdown_stops_tunnel_but_keeps_mode(make_office, tmp_path, monkeypatch):
    office = make_office()
    remote, s = make_remote(tmp_path)
    remote.update({"mode": "tunnel"})
    exits = []
    monkeypatch.setattr("office.server.threading.Timer", lambda delay, fn, args: type("T", (), {"start": lambda self: exits.append(args)})())
    c = TestClient(create_app(office, remote=remote), base_url=LOCAL)
    assert c.post("/api/shutdown").json() == {"ok": True} and exits == [[0]]
    assert ("tunnel-stop",) in s.calls and ("server-stop", "127.0.0.1") in s.calls  # 퇴근하면 터널 프로그램도 같이 끈다
    again, _ = make_remote(tmp_path)
    assert again.mode == "tunnel"  # 다음에 켤 때는 다시 연다
