"""바탕화면 아이콘이 실행하는 파일 (pythonw: 콘솔 창 없음). --background: 윈도우 시작 때 창 없이 서버만."""
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

from office.config import BROWSERS, DATA, HOST, OLLAMA_URL, PORT

DATA.mkdir(parents=True, exist_ok=True)
# pythonw는 stdout이 None이라 uvicorn 로그가 터진다 → 로그 파일로 돌린다
sys.stdout = sys.stderr = open(DATA / "office.log", "a", encoding="utf-8", buffering=1)

URL = f"http://{HOST}:{PORT}/"
BACKGROUND = "--background" in sys.argv


def is_up(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1):
            return True
    except OSError:
        return False


def wait_for(url: str, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if is_up(url):
            return True
        time.sleep(0.5)
    return False


def ensure_ollama() -> None:
    if is_up(f"{OLLAMA_URL}/api/version"):
        return
    try:
        subprocess.Popen(["ollama", "serve"], creationflags=subprocess.CREATE_NO_WINDOW,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        print(f"ollama를 못 켰어: {e}")  # 화면의 상태등이 'Ollama 꺼짐'으로 알려줌
        return
    if not wait_for(f"{OLLAMA_URL}/api/version", 20):
        print("ollama가 20초 안에 안 떴어")


def open_window() -> None:
    browser = next((b for b in BROWSERS if b.exists()), None)
    if browser:
        subprocess.Popen([str(browser), f"--app={URL}", "--window-size=1440,900"])
    else:
        webbrowser.open(URL)


def main() -> None:
    # 첫 화면(정적 파일)으로 확인: /api/state는 Ollama 확인 때문에 1초를 넘길 수 있다
    if is_up(URL):
        if not BACKGROUND:
            open_window()  # 두 번 눌러도 서버는 하나
        return
    ensure_ollama()

    def open_when_ready() -> None:
        if wait_for(f"{URL}api/state", 30):
            open_window()
        else:
            print("사무실 서버가 30초 안에 안 떴어")

    if not BACKGROUND:
        threading.Thread(target=open_when_ready, daemon=True).start()
    import uvicorn

    # 접근 로그는 끔: 화면이 1초마다 상태를 물어서 오류 기록이 묻힌다
    uvicorn.run("office.server:app", host=HOST, port=PORT, access_log=False)


if __name__ == "__main__":
    main()
