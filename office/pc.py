"""실장님이 PC에서 쓰는 손: 웹 가져오기, 화면 캡처, 클립보드, 볼륨·음악 키, 배터리. 전부 읽기이거나 되돌릴 수 있는 일."""
import ctypes
import os
import re
import subprocess
import urllib.request

from office import OfficeError

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ritual-rab/2.0"
MAX_PAGE = 2_000_000
KEYS = {"volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD, "play_pause": 0xB3, "next": 0xB0, "previous": 0xB1}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read(MAX_PAGE + 1)
            charset = resp.headers.get_content_charset() or "utf-8"
    except OSError as e:
        raise OfficeError("그 주소를 못 열었어요. 인터넷 연결이나 주소를 확인해 주세요.") from e
    return data[:MAX_PAGE].decode(charset, "replace")


def grab_screen() -> bytes:
    from PIL import ImageGrab

    from office.scan import _normalize

    return _normalize(ImageGrab.grab(all_screens=True))


def look(question: str, image: bytes) -> str:
    from office import llm

    system = "너는 대표님의 화면을 보는 AI 비서다. 화면에 보이는 것만 근거로 짧고 정확하게 한국어 존댓말로 답한다."
    return llm.chat(system, question or "화면에 무엇이 있나요?", images=[image], temperature=0.2).strip()


def clipboard(text: str | None = None) -> str:
    """text가 있으면 복사, 없으면 지금 클립보드 글자. 글자는 환경 변수로 넘긴다 (명령어에 안 섞이게)."""
    if text is not None:
        env = {**os.environ, "RITUAL_CLIP": text}
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", "Set-Clipboard -Value $env:RITUAL_CLIP"],
                       env=env, capture_output=True, timeout=15, creationflags=NO_WINDOW)
        return text
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                          "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Clipboard -Raw"],
                         capture_output=True, timeout=15, creationflags=NO_WINDOW)
    return out.stdout.decode("utf-8", "replace").strip()


def press(key: str) -> None:
    vk = KEYS[key]
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # 2 = KEYEVENTF_KEYUP


def battery() -> dict | None:
    class Status(ctypes.Structure):
        _fields_ = [("ac", ctypes.c_byte), ("flag", ctypes.c_byte), ("percent", ctypes.c_byte), ("saver", ctypes.c_byte),
                    ("life", ctypes.c_ulong), ("full", ctypes.c_ulong)]
    try:
        s = Status()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
            return None
    except (AttributeError, OSError):
        return None
    return {"percent": None if s.percent == -1 else s.percent & 0xFF, "plugged_in": s.ac == 1}


def strip_tags(text: str) -> str:
    import html

    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", text)).split())  # 검색 결과의 <b>굵게</b>는 붙여서

