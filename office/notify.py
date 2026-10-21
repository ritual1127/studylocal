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
from urllib.parse import urlsplit
from collections import deque
from pathlib import Path
from xml.sax.saxutils import escape

from office import OfficeError
from office.config import HOST, PORT, WEB

AUMID = "Ritual.StudyOffice"
DEFAULTS = {"pc": True, "phone": False, "topic": "", "server": "https://ntfy.sh", "job_done": True, "briefing": "07:30",
            "ai": "fast"}
AI_MODES = ("fast", "careful")
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
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "ritual's rab")
        winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, str(WEB / "icon.ico"))


def ntfy_root(url: str) -> str:
    """ntfy JSON 보내기는 서버 루트로만 된다. 주제까지 적힌 구독 주소가 들어와도 루트만 남긴다."""
    parts = urlsplit(str(url).strip())
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else DEFAULTS["server"]


def post_json(url: str, payload: dict) -> None:
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
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
        self.settings["server"] = ntfy_root(self.settings["server"])  # 예전에 잘못 저장된 주소도 고친다

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
                new["server"] = ntfy_root(server)
            if "briefing" in changes:
                briefing = str(changes["briefing"]).strip()
                if briefing and not TIME.fullmatch(briefing):
                    raise OfficeError("아침 브리핑 시각은 07:30처럼 써줘.")
                new["briefing"] = briefing
            if "ai" in changes:
                if changes["ai"] not in AI_MODES:
                    raise OfficeError("AI 모드는 빠름·꼼꼼 중 하나야.")
                new["ai"] = changes["ai"]
            if changes.get("new_topic") or (new["phone"] and not new["topic"]):
                new["topic"] = "ritual-" + secrets.token_urlsafe(16)  # 주제 이름 = 비밀번호 역할
            self.settings = new
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(new, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
            return dict(new)

    def reset(self) -> dict:
        """설정 기본값으로 (폰 주제·서버는 남겨서 다시 켜면 구독이 그대로)."""
        keep = {"topic": self.settings["topic"], "server": self.settings["server"]}
        with self.lock:
            self.settings = {**DEFAULTS, **keep}
        return self.update({})

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
        self.post(ntfy_root(s["server"]), {"topic": s["topic"], "title": title, "message": body,
                                "priority": 4 if reminder else 3, "tags": ["alarm_clock" if reminder else "books"]})

    def send(self, title: str, body: str, reminder: bool = False, only: str | None = None) -> list[str]:
        """켜 둔 곳에 모두 (only="pc"·"phone"이면 그곳만) 보낸다. 실패해도 예외 대신 에러 목록을 돌려준다."""
        s = self.settings
        errors = []
        channels = [("PC", "pc", s["pc"], self._pc), ("폰", "phone", s["phone"] and bool(s["topic"]), self._phone)]
        for name, key, enabled, sender in channels:
            if only and key != only:
                continue
            if not enabled:
                if only:
                    errors.append(f"{name}: {name} 알림이 꺼져 있어. 설정에서 켜줘.")
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
