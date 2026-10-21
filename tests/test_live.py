import json, os, subprocess, time
from pathlib import Path
import pytest
from office.config import BROWSERS, DATA
from office.literature import fetch_literature
from office.note import make_pdf
from office.quiz import make_quiz_page
from office.scan import scan

pytestmark = pytest.mark.skipif(os.environ.get("RITUAL_LIVE") != "1", reason="실제 Ollama 실측은 RITUAL_LIVE=1일 때만")
HANDOUT = Path(__file__).parent / "fixtures" / "handout.html"

def test_handout_to_pdf_and_quiz(tmp_path):
    shot = tmp_path / "handout.png"
    browser = next(p for p in BROWSERS if p.exists())
    subprocess.run([str(browser), "--headless", "--disable-gpu", "--window-size=1240,1754",
                    f"--user-data-dir={DATA / 'edge-headless'}", f"--screenshot={shot}", HANDOUT.as_uri()], timeout=60)
    t0 = time.perf_counter(); m = scan([shot]); t1 = time.perf_counter()
    assert "미토콘드리아" in m.markdown and "세포막" in m.markdown
    pdf = make_pdf(m, tmp_path); t2 = time.perf_counter()
    make_quiz_page(m, 5, tmp_path); t3 = time.perf_counter()
    quiz = json.loads((tmp_path / "quiz" / "quiz.json").read_text(encoding="utf-8"))
    assert pdf.exists() and len(quiz["questions"]) >= 3
    print(f"\n[실측] OCR {t1 - t0:.0f}초 / PDF {t2 - t1:.0f}초 / 문제 5개 {t3 - t2:.0f}초")

def test_literature_public_domain():
    t0 = time.perf_counter()
    m = fetch_literature("운수 좋은 날")
    assert m.original and m.original.startswith("새침하게") and m.markdown
    print(f"\n[실측] 작품 가져오기 {time.perf_counter() - t0:.0f}초")
