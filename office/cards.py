"""암기담당: 암기카드 웹 + Anki로 가져갈 수 있는 CSV."""
import csv
import html
import json
from pathlib import Path

from office import Material, OfficeError, fill, quiet
from office.config import GALMURI_CSS
from office.llm import chat_json, clip

CARDS_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "cards": {"type": "array", "items": {
            "type": "object",
            "properties": {"front": {"type": "string"}, "back": {"type": "string"}},
            "required": ["front", "back"]}},
    },
    "required": ["title", "cards"],
}

CARDS_SYSTEM = """너는 '공부 사무실'의 암기담당 직원이다. 자료에서 꼭 외워야 할 것만 골라 암기카드를 만든다.
front는 용어·질문(짧게), back은 뜻·답(한두 문장). 자료에 없는 내용은 넣지 않는다. 중복 없이.
title에는 카드 묶음의 짧은 제목을 쓴다. JSON으로만 답한다."""


def validate_cards(raw: dict) -> dict:
    seen, cards = set(), []
    for card in raw.get("cards") or []:
        if not isinstance(card, dict):
            continue
        front = " ".join(str(card.get("front") or "").split())[:120]
        back = " ".join(str(card.get("back") or "").split())[:400]
        if not front or not back or front in seen:
            continue
        seen.add(front)
        cards.append({"front": front, "back": back})
    if len(cards) < 3:
        raise OfficeError("쓸 만한 카드가 3장도 안 나왔어. 다시 시도해줘.")
    return {"title": str(raw.get("title") or "").strip()[:60] or "암기카드", "cards": cards}


def make_cards_page(material: Material, count: int, job_dir: Path, llm=chat_json, say=quiet,
                    feedback: str = "") -> Path:
    say(f"암기카드 {count}장 만드는 중")
    user = f"카드 수: {count}\n\n{clip(material.markdown)}"
    if feedback:
        user += f"\n\n[대표 수정 요청] {feedback}"
    deck = validate_cards(llm(CARDS_SYSTEM, user, CARDS_SCHEMA, temperature=0.2))
    deck["cards"] = deck["cards"][:count]
    folder = Path(job_dir) / "cards"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "cards.json").write_text(json.dumps(deck, ensure_ascii=False, indent=1), encoding="utf-8")
    with (folder / "cards.csv").open("w", encoding="utf-8-sig", newline="") as f:  # Anki·엑셀이 한글을 알아보게 BOM
        csv.writer(f).writerows([c["front"], c["back"]] for c in deck["cards"])
    page = folder / "index.html"
    page.write_text(fill("cards.html", title=html.escape(deck["title"]), galmuri_css=GALMURI_CSS,
                         deck_json=json.dumps(deck, ensure_ascii=False).replace("<", "\\u003c")), encoding="utf-8")
    say(f"카드 {len(deck['cards'])}장 완성")
    return page
