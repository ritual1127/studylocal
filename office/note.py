import datetime
import html
import subprocess
from pathlib import Path

from office import Material, OfficeError, fill, quiet
from office.config import BROWSERS, DATA, FONTS, PALETTE, WEB
from office.llm import chat_json, clip

NOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "subtitle": {"type": "string"},
        "sections": {"type": "array", "items": {
            "type": "object",
            "properties": {"heading": {"type": "string"},
                           "points": {"type": "array", "items": {"type": "string"}},
                           "highlight": {"type": "string"}},
            "required": ["heading", "points", "highlight"]}},
        "key_terms": {"type": "array", "items": {
            "type": "object",
            "properties": {"term": {"type": "string"}, "meaning": {"type": "string"}},
            "required": ["term", "meaning"]}},
        "summary": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "subtitle", "sections", "key_terms", "summary"],
}

NOTE_SYSTEM = """너는 '공부 사무실'의 디자이너 직원이다. 자료를 공부 노트 구조로 재배치한다.
자료의 내용은 빠뜨리지 않고, 자료에 없는 내용은 절대 추가하지 않는다.
sections는 자료의 흐름 순서대로, points는 짧은 문장으로, highlight는 그 섹션의 핵심 한 문장(없으면 빈 문자열)으로 쓴다.
key_terms에는 자료에 나온 용어만 넣고, summary는 3~5줄로 쓴다. JSON으로만 답한다."""


def make_note(material: Material, llm=chat_json) -> dict:
    note = llm(NOTE_SYSTEM, clip(material.markdown), NOTE_SCHEMA, temperature=0.2)
    if not note.get("sections"):
        raise OfficeError("정리할 내용이 없어.")
    return note


def _e(text) -> str:
    return html.escape(str(text or ""))


def render_note_html(note: dict, material: Material) -> str:
    sections = []
    for i, sec in enumerate(note.get("sections", [])):
        points = "".join(f"<li>{_e(p)}</li>" for p in sec.get("points", []) if str(p).strip())
        highlight = f'<div class="highlight"><b>핵심</b>{_e(sec["highlight"])}</div>' if sec.get("highlight") else ""
        sections.append(f'<section class="part" style="--c:{PALETTE[i % len(PALETTE)]}">'
                        f'<h2>{_e(sec.get("heading"))}</h2><ul>{points}</ul>{highlight}</section>')
    terms = note.get("key_terms") or []
    terms_html = ('<div class="box-title">용어 정리</div><table class="terms">'
                  + "".join(f"<tr><th>{_e(t.get('term'))}</th><td>{_e(t.get('meaning'))}</td></tr>" for t in terms)
                  + "</table>") if terms else ""
    summary = note.get("summary") or []
    summary_html = ('<div class="summary"><div class="box-title">한눈에 정리</div><ul>'
                    + "".join(f"<li>{_e(s)}</li>" for s in summary) + "</ul></div>") if summary else ""
    sources_html = (f'<p class="sources">출처: {_e(", ".join(material.sources))}</p>') if material.sources else ""
    original_html = (f'<section class="original"><h2>원문</h2>'
                     f'<div class="original-text">{_e(material.original)}</div></section>') if material.original else ""
    logo = WEB / "logo-pixel.png"
    return fill("note.html",
                title=_e(note.get("title") or material.title),
                subtitle=_e(note.get("subtitle")),
                logo=f'<img src="{logo.as_uri()}" alt="ritual">' if logo.exists() else "",
                bar='<div class="bar">' + "".join(f'<span style="background:{c}"></span>' for c in PALETTE) + "</div>",
                sections="".join(sections), terms=terms_html, summary=summary_html,
                sources=sources_html, original=original_html,
                date=datetime.date.today().isoformat(),
                font_regular=(FONTS / "Galmuri11.woff2").as_uri(),
                font_bold=(FONTS / "Galmuri11-Bold.woff2").as_uri())


def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    browser = next((p for p in BROWSERS if p.exists()), None)
    if browser is None:
        raise OfficeError("PDF를 만들려면 Edge나 Chrome이 필요해.")
    pdf_path.unlink(missing_ok=True)
    # 따로 쓰는 프로필: 이미 켜진 Edge 창에 붙지 않게
    cmd = [str(browser), "--headless", "--disable-gpu", "--no-first-run", "--no-pdf-header-footer",
           f"--user-data-dir={DATA / 'edge-headless'}", f"--print-to-pdf={pdf_path}", html_path.as_uri()]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    if not pdf_path.exists() or pdf_path.read_bytes()[:4] != b"%PDF":
        last = (result.stderr.strip().splitlines() or ["알 수 없는 오류"])[-1]
        raise OfficeError(f"PDF 만들기 실패: {last}")


def make_pdf(material: Material, job_dir: Path, llm=chat_json, say=quiet) -> Path:
    say("노트 구조 잡는 중")
    note = make_note(material, llm=llm)
    html_path = job_dir / "note.html"
    html_path.write_text(render_note_html(note, material), encoding="utf-8")
    say("PDF 인쇄 중")
    pdf_path = job_dir / "note.pdf"
    html_to_pdf(html_path, pdf_path)
    return pdf_path
