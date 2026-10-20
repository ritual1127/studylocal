import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
WEB = ROOT / "web"
FONTS = WEB / "fonts"
LOGO = ROOT / "assets" / "ritual-wordmark.png"
DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ritual-office"

OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = os.environ.get("RITUAL_MODEL", "qwen3.5:latest")
NUM_CTX = 16384
MAX_INPUT_CHARS = 8000
MAX_IMAGE_SIDE = 1600
MAX_PAGES = 20

HOST, PORT = "127.0.0.1", 8765
BROWSERS = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")]
PALETTE = ["#9337FD", "#E036F0", "#FC34CA", "#FD389C", "#FD633E", "#FC7135"]
GALMURI_CSS = "https://cdn.jsdelivr.net/npm/galmuri@2.40.3/dist/galmuri.css"
