"""윈도우를 켤 때 사무실 서버를 창 없이 켜는 시작프로그램 바로가기 (알림을 받으려면 PC에서 서버가 돌고 있어야 한다)."""
import base64
import os
import subprocess
import sys
from pathlib import Path

from office.config import ROOT, WEB

NAME = "ritual의 공부 사무실 (자동 시작).lnk"
# 글자는 전부 환경 변수로 넘긴다 → 경로에 따옴표가 있어도 명령어가 깨지거나 주입되지 않는다
SCRIPT = r"""
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:RITUAL_LNK)
$s.TargetPath = $env:RITUAL_TARGET
$s.Arguments = $env:RITUAL_ARGS
$s.WorkingDirectory = $env:RITUAL_DIR
$s.IconLocation = $env:RITUAL_ICON
$s.WindowStyle = 7
$s.Save()
"""


def shortcut_path() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / NAME


def is_enabled(path: Path | None = None) -> bool:
    return (path or shortcut_path()).exists()


def set_enabled(on: bool, path: Path | None = None, run=subprocess.run) -> bool:
    path = path or shortcut_path()
    if not on:
        path.unlink(missing_ok=True)
        return False
    pythonw = Path(sys.executable).with_name("pythonw.exe")  # 앱 가상환경의 pythonw: 콘솔 창 없음
    env = {**os.environ, "RITUAL_LNK": str(path), "RITUAL_TARGET": str(pythonw),
           "RITUAL_ARGS": f'"{ROOT / "launch.pyw"}" --background', "RITUAL_DIR": str(ROOT), "RITUAL_ICON": str(WEB / "icon.ico")}
    script = base64.b64encode(SCRIPT.encode("utf-16-le")).decode("ascii")
    run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", script],
        env=env, capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return is_enabled(path)
