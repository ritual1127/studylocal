"""번역가: 자료를 문단별로 번역해 원문과 나란히 보여준다."""
import html
import json
from itertools import zip_longest
from pathlib import Path

from office import Material, OfficeError, fill, quiet
from office.config import GALMURI_CSS, MAX_INPUT_CHARS
from office.llm import chat_json
from office.note import with_feedback

MAX_PARAGRAPHS = 80
TRANSLATE_SCHEMA = {"type": "object",
                    "properties": {"translations": {"type": "array", "items": {"type": "string"}}},
                    "required": ["translations"]}

TRANSLATOR_SYSTEM = """너는 '공부 사무실'의 번역가 직원이다. 번호가 붙은 문단을 하나씩 자연스럽게 번역한다.
translations 배열에 번호 순서대로, 문단 개수와 똑같이 넣는다. 문단을 합치거나 빼지 않는다.
제목 기호(#)·목록 기호(-)·표 기호(|)는 그대로 두고 글만 번역한다. 설명은 붙이지 않는다. JSON으로만 답한다."""


def _paragraphs(markdown: str) -> list[str]:
    out, total = [], 0
    for line in markdown.splitlines():
        line = line.strip()
        if not line or line == "---":
            continue
        if len(out) >= MAX_PARAGRAPHS or total + len(line) > MAX_INPUT_CHARS:
            break
        out.append(line)
        total += len(line)
    return out


def pick_target(text: str, target: str) -> str:
    """말한 언어가 없으면: 한국어 자료는 영어로, 외국어 자료는 한국어로."""
    if target.strip():
        return target.strip()[:20]
    letters = [ch for ch in text if ch.isalpha()]
    hangul = sum("가" <= ch <= "힣" for ch in letters)
    return "영어" if letters and hangul / len(letters) > 0.3 else "한국어"


def make_translation_page(material: Material, target: str, job_dir: Path, llm=chat_json, say=quiet,
                          feedback: str = "") -> Path:
    paragraphs = _paragraphs(material.markdown)
    if not paragraphs:
        raise OfficeError("번역할 글이 없어.")
    target = pick_target(material.markdown, target)
    say(f"{target}로 {len(paragraphs)}문단 번역 중")
    user = f"{target}로 번역해줘.\n\n" + "\n".join(f"[{i}] {p}" for i, p in enumerate(paragraphs, 1))
    raw = llm(TRANSLATOR_SYSTEM, with_feedback(user, feedback), TRANSLATE_SCHEMA, temperature=0.2)
    done = [" ".join(t.split()) if isinstance(t, str) else "" for t in raw.get("translations") or []]
    if not any(done):
        raise OfficeError("번역을 못 했어. 다시 시도해줘.")
    # 개수가 어긋나면 남는 원문 옆은 빈칸, 남는 번역은 버린다
    pairs = [{"original": o, "translated": t} for o, t in zip_longest(paragraphs, done[:len(paragraphs)], fillvalue="")]
    data = {"title": material.title, "target": target, "pairs": pairs}
    folder = Path(job_dir) / "translation"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "translation.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (folder / "translation.md").write_text("\n\n".join(p["translated"] for p in pairs if p["translated"]), encoding="utf-8")
    page = folder / "index.html"
    page.write_text(fill("translation.html", title=html.escape(material.title or "번역"), galmuri_css=GALMURI_CSS,
                         data_json=json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")), encoding="utf-8")
    say(f"{target} 번역 끝")
    return page
