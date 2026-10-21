"""폰 원격: 토큰이 있어야 들어오는 두 번째 서버(8766). 같은 와이파이 / 어디서나(Cloudflare 임시 터널).

내 PC를 밖에 여는 일이라 기본은 꺼짐이고, 대표가 설정에서 직접 켠다.
"""
import hmac
import json
import re
import secrets
import socket
import subprocess
import threading
import traceback
import urllib.request
from pathlib import Path

from office import OfficeError
from office.config import DATA

REMOTE_PORT = 8766
MODES = ("off", "lan", "tunnel")
TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
CLOUDFLARED = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"


def find_tunnel_url(line: str) -> str | None:
    m = TUNNEL_URL.search(line)
    return m.group(0) if m and m.group(0) != "https://api.trycloudflare.com" else None


def lan_addresses() -> list[str]:
    """이 PC의 사설 IP (공유기 안 주소)."""
    try:
        infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
    except OSError:
        return []
    ips = sorted({info[4][0] for info in infos})
    private = re.compile(r"(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)")
    return [ip for ip in ips if private.match(ip)]


def start_uvicorn(app_factory, host: str):
    """폰 서버를 다른 스레드에서 띄우고, 끄는 함수를 돌려준다."""
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app_factory(), host=host, port=REMOTE_PORT, log_level="warning", access_log=False))
    thread = threading.Thread(target=server.run, daemon=True, name="office-remote")
    thread.start()

    def stop():
        server.should_exit = True
        thread.join(timeout=5)
    return stop


def cloudflared_path() -> Path:
    exe = DATA / "cloudflared.exe"
    if not exe.exists():  # 처음 켤 때 한 번 내려받는다 (공식 GitHub 배포본)
        DATA.mkdir(parents=True, exist_ok=True)
        part = exe.with_suffix(".part")
        try:
            urllib.request.urlretrieve(CLOUDFLARED, part)
        except OSError as e:
            raise OfficeError("Cloudflare 터널 프로그램을 못 내려받았어. 인터넷 연결을 확인해줘.") from e
        part.replace(exe)
    return exe


def start_cloudflared(on_url):
    proc = subprocess.Popen([str(cloudflared_path()), "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{REMOTE_PORT}"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def read():
        for line in proc.stdout:
            if url := find_tunnel_url(line):
                on_url(url)
    threading.Thread(target=read, daemon=True, name="office-tunnel").start()

    def stop():
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    return stop


class Remote:
    def __init__(self, path: Path, *, start_server, start_tunnel=start_cloudflared, notify=lambda title, body: None,
                 lan=lan_addresses):
        self.path = Path(path)
        self.start_server, self.start_tunnel, self.notify, self.lan = start_server, start_tunnel, notify, lan
        self.lock = threading.RLock()
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        saved = saved if isinstance(saved, dict) else {}
        self.mode = saved.get("mode") if saved.get("mode") in MODES else "off"
        token = saved.get("token")
        self.token = token if isinstance(token, str) and len(token) >= 32 else secrets.token_urlsafe(32)
        self.tunnel_url = ""
        self.error = ""
        self._stops: list = []

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"mode": self.mode, "token": self.token}), encoding="utf-8")
        tmp.replace(self.path)

    def check(self, token) -> bool:
        return self.mode != "off" and isinstance(token, str) and hmac.compare_digest(token.encode(), self.token.encode())

    def update(self, changes: dict) -> dict:
        with self.lock:
            mode = changes.get("mode", self.mode)
            if mode not in MODES:
                raise OfficeError("연결 방식은 끔·같은 와이파이·어디서나 중 하나야.")
            if changes.get("new_token"):
                self.token = secrets.token_urlsafe(32)
            restart = mode != self.mode
            self.mode = mode
            self._save()
            if restart:
                self.apply()
            elif changes.get("new_token") and self.tunnel_url:
                self._tell_phone()
            return self.status()

    def close(self) -> None:
        """폰 서버·터널 프로그램을 끈다. 모드는 그대로 둬서 다음에 켤 때 다시 연다 (퇴근할 때)."""
        with self.lock:
            for stop in reversed(self._stops):
                try:
                    stop()
                except Exception:
                    traceback.print_exc()
            self._stops, self.tunnel_url = [], ""

    def apply(self) -> None:
        """지금 모드대로 폰 서버와 터널을 켜고 끈다 (사무실을 켤 때도 부른다)."""
        with self.lock:
            self.close()
            self.error = ""
            if self.mode == "off":
                return
            try:
                self._stops.append(self.start_server("0.0.0.0" if self.mode == "lan" else "127.0.0.1"))
                if self.mode == "tunnel":
                    self._stops.append(self.start_tunnel(self._on_tunnel))
            except (OfficeError, OSError) as e:
                self.error = str(e) if isinstance(e, OfficeError) else f"폰 연결을 못 켰어 ({type(e).__name__})"

    def _on_tunnel(self, url: str) -> None:
        self.tunnel_url = url
        self._tell_phone()

    def _tell_phone(self) -> None:
        self.notify("폰 접속 주소", f"{self.tunnel_url}/m?k={self.token}")  # 터널 주소는 켤 때마다 바뀐다

    def status(self) -> dict:
        if self.mode == "tunnel":
            bases = [self.tunnel_url] if self.tunnel_url else []
        elif self.mode == "lan":
            bases = [f"http://{ip}:{REMOTE_PORT}" for ip in self.lan()]
        else:
            bases = []
        return {"mode": self.mode, "urls": bases, "link": f"{bases[0]}/m?k={self.token}" if bases else "",
                "starting": self.mode == "tunnel" and not self.tunnel_url and not self.error, "error": self.error}
