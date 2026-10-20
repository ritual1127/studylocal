import pytest
from office import Material, OfficeError
from office.config import BROWSERS
from office.note import make_note, render_note_html, html_to_pdf

SAMPLE_NOTE = {"title": "세포의 구조", "subtitle": "생명과학 1단원",
               "sections": [{"heading": "핵", "points": ["유전 물질 보관", "<script>alert(1)</script>"], "highlight": "핵 = 세포의 사령부"}],
               "key_terms": [{"term": "핵막", "meaning": "핵을 감싸는 막"}], "summary": ["세포는 생명의 기본 단위"]}

def test_note_html_escapes_and_contains_content():
    html = render_note_html(SAMPLE_NOTE, Material(title="세포의 구조", markdown="", sources=["1.jpg"]))
    for text in ["세포의 구조", "핵 = 세포의 사령부", "핵막", "세포는 생명의 기본 단위", "1.jpg"]:
        assert text in html
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html

def test_original_section_only_when_present():
    with_original = render_note_html(SAMPLE_NOTE, Material(title="t", markdown="", original="새침하게 흐린 품이"))
    assert 'class="original"' in with_original and "새침하게 흐린 품이" in with_original
    assert 'class="original"' not in render_note_html(SAMPLE_NOTE, Material(title="t", markdown=""))

def test_make_note_rejects_empty():
    empty = {"title": "t", "subtitle": "", "sections": [], "key_terms": [], "summary": []}
    with pytest.raises(OfficeError):
        make_note(Material(title="t", markdown="x"), llm=lambda *a, **k: empty)

@pytest.mark.skipif(not any(p.exists() for p in BROWSERS), reason="Edge/Chrome 없음")
def test_pdf_has_korean_fonts(tmp_path):
    folder = tmp_path / "한글 폴더"; folder.mkdir()
    html = folder / "note.html"
    html.write_text(render_note_html(SAMPLE_NOTE, Material(title="세포의 구조", markdown="")), encoding="utf-8")
    pdf = folder / "note.pdf"
    html_to_pdf(html, pdf)
    data = pdf.read_bytes()
    assert data[:4] == b"%PDF" and b"Galmuri" in data and b"Malgun" in data
