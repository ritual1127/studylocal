"""조사원: 개념·인물·사건을 한국어 위키백과에서 조사한다 (문학 작품 원문은 사서 담당)."""
import re

from office import Material, OfficeError, quiet
from office.config import MAX_INPUT_CHARS
from office.literature import WIKIPEDIA, _get_json, _search, page_url, pick_title


def _headings(text: str) -> str:
    # 위키 문법 "== 과정 ==" → 마크다운 "## 과정"
    return re.sub(r"^(=+)\s*(.+?)\s*=+\s*$", lambda m: "#" * min(len(m.group(1)), 4) + " " + m.group(2),
                  text, flags=re.MULTILINE)


def research(topic: str, get_json=_get_json, say=quiet) -> Material:
    say(f"'{topic}' 조사 중")
    hits = _search(get_json, WIKIPEDIA, topic)
    title = pick_title(topic, hits) or (hits[0] if hits else None)
    if not title:
        raise OfficeError(f"'{topic}'에 대한 자료를 못 찾았어. 다른 말로 써줘.")
    data = get_json(WIKIPEDIA, {"action": "query", "prop": "extracts", "explaintext": 1, "redirects": 1, "titles": title})
    pages = data.get("query", {}).get("pages", [])
    extract = (pages[0].get("extract") or "").strip() if pages else ""
    if not extract:
        raise OfficeError(f"'{topic}'에 대한 자료를 못 찾았어. 다른 말로 써줘.")
    say(f"'{title}' 자료 찾았어")
    warnings = []
    if len(extract) > MAX_INPUT_CHARS:
        warnings.append(f"자료가 길어서({len(extract):,}자) 앞부분 위주로 정리해.")
    return Material(title=title, markdown=f"# {title}\n\n{_headings(extract)}", sources=[page_url(WIKIPEDIA, title)],
                    warnings=warnings)
