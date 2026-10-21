"""알림: PC는 Windows 토스트, 폰은 ntfy 앱 푸시."""
import base64
import datetime
import json
import os
import re
import secrets
import subprocess
import threading
import urllib.request
from collections import deque
from pathlib import Path
from xml.sax.saxutils import escape

from office import OfficeError
from office.config import HOST, PORT, WEB

AUMID = "Ritual.StudyOffice"
DEFAULTS = {"pc": True, "phone": False, "topic": "", "server": "https://ntfy.sh", "job_done": True, "briefing": "07:30"}
TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d")

# 글자는 XML로 이스케이프해서 환경 변수로 넘긴다 → 명령어 주입 없음
TOAST_PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($env:RITUAL_TOAST)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:RITUAL_AUMID).Show((New-Object Windows.UI.Notifications.ToastNotification $xml))
"""


def toast_xml(title: str, body: str, reminder: bool = False) -> str:
    sound = "Notification.Reminder" if reminder else "Notification.Default"
    return (f'<toast activationType="protocol" launch="http://{HOST}:{PORT}/">'
            f'<visual><binding template="ToastGeneric"><text>{escape(title)}</text><text>{escape(body)}</text>'
            f'</binding></visual><audio src="ms-winsoundevent:{sound}"/></toast>')


def register_app() -> None:
    """토스트에 'ritual의 공부 사무실' 이름과 아이콘이 뜨게 앱 ID를 등록한다 (사용자 레지스트리)."""
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\AppUserModelId\{AUMID}") as key:
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "ritual의 공부 사무실")
        winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(WEB / "icon.ico"))


def post_json(url: str, payload: dict) -> None:
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except OSError as e:
        raise OfficeError("인터넷 연결을 확인해줘.") from e


class Notifier:
    def __init__(self, path: Path, run=subprocess.run, post=post_json, register=register_app):
        self.path, self.run, self.post, self.register = Path(path), run, post, register
        self.lock = threading.Lock()
        self.registered = False
        self.history: deque = deque(maxlen=20)
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        self.settings = {k: saved.get(k, v) if type(saved.get(k, v)) is type(v) else v for k, v in DEFAULTS.items()}

    def update(self, changes: dict) -> dict:
        with self.lock:
            new = dict(self.settings)
            for key in ("pc", "phone", "job_done"):
                if key in changes:
                    if not isinstance(changes[key], bool):
                        raise OfficeError("켜기/끄기 값이 이상해.")
                    new[key] = changes[key]
            if "server" in changes:
                server = str(changes["server"]).strip().rstrip("/")
                if not re.fullmatch(r"https?://[^\s/]+(/[^\s]*)?", server):
                    raise OfficeError("ntfy 서버 주소는 https://로 시작해야 해.")
                new["server"] = server
            if "briefing" in changes:
                briefing = str(changes["briefing"]).strip()
                if briefing and not TIME.fullmatch(briefing):
                    raise OfficeError("아침 브리핑 시각은 07:30처럼 써줘.")
                new["briefing"] = briefing
            if changes.get("new_topic") or (new["phone"] and not new["topic"]):
                new["topic"] = "ritual-" + secrets.token_urlsafe(16)  # 주제 이름 = 비밀번호 역할
            self.settings = new
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
            return dict(new)

    def _pc(self, title: str, body: str, reminder: bool) -> None:
        if not self.registered:
            self.register()
            self.registered = True
        script = base64.b64encode(TOAST_PS.encode("utf-16-le")).decode("ascii")
        env = {**os.environ, "RITUAL_TOAST": toast_xml(title, body, reminder), "RITUAL_AUMID": AUMID}
        self.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", script],
                 env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), capture_output=True, timeout=30)

    def _phone(self, title: str, body: str, reminder: bool) -> None:
        s = self.settings
        self.post(s["server"], {"topic": s["topic"], "title": title, "message": body,
                                "priority": 4 if reminder else 3, "tags": ["alarm_clock" if reminder else "books"]})

    def send(self, title: str, body: str, reminder: bool = False) -> list[str]:
        """켜 둔 곳에 모두 보낸다. 실패해도 예외 대신 에러 목록을 돌려준다."""
        s = self.settings
        errors = []
        channels = [("PC", s["pc"], self._pc), ("폰", s["phone"] and bool(s["topic"]), self._phone)]
        for name, enabled, sender in channels:
            if not enabled:
                continue
            try:
                sender(title, body, reminder)
            except OfficeError as e:
                errors.append(f"{name}: {e}")
            except (OSError, subprocess.SubprocessError) as e:
                errors.append(f"{name}: 알림을 못 보냈어 ({type(e).__name__})")
        self.history.appendleft({"time": f"{datetime.datetime.now():%m-%d %H:%M}", "title": title,
                                 "body": body, "errors": errors})
        return errors
