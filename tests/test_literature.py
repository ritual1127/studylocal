from pathlib import Path
from urllib.parse import unquote
import pytest
from office import OfficeError
from office.literature import WIKISOURCE, html_to_text, pick_title, fetch_literature

FIXTURE = Path(__file__).parent / "fixtures" / "wikisource_unsu.html"

def test_html_to_text_on_real_page():
    text = html_to_text(FIXTURE.read_text(encoding="utf-8"))
    assert text.startswith("새침하게 흐린 품이")
    assert text.endswith("”") and "라이선스" not in text[-50:]
    assert "{" not in text and len(text) > 5000

def test_html_to_text_keeps_poem_lines():
    html = '<div class="ws-noexport">머리말</div><div class="poem"><p>나 보기가 역겨워<br>가실 때에는<br></p></div>'
    assert html_to_text(html) == "나 보기가 역겨워\n가실 때에는"

def test_pick_title():
    assert pick_title("운수 좋은 날", ["운수 좋은 날", "서울특별시 택시운수종사자 복지시설"]) == "운수 좋은 날"
    assert pick_title("운수 좋은 날 현진건", ["운수 좋은 날"]) == "운수 좋은 날"
    assert pick_title("소나기", ["서울특별시 조례"]) is None

def fake_get_json(source=True, wiki=True):
    def get(host, params):
        if params.get("list") == "search":
            found = source if host == WIKISOURCE else wiki
            return {"query": {"search": [{"title": "운수 좋은 날"}] if found else []}}
        if params.get("action") == "parse":
            return {"parse": {"text": "<p>새침하게 흐린 품이 눈이 올 듯하더니</p>"}}
        return {"query": {"pages": [{"extract": "현진건의 단편소설이다."}]}}
    return get

def test_public_domain_work_keeps_original():
    seen = {}
    def llm(system, user, **kw):
        seen["user"] = user
        return "## 작품 정보\n현진건"
    m = fetch_literature("운수 좋은 날", llm=llm, get_json=fake_get_json())
    assert m.original.startswith("새침하게") and "현진건의 단편소설" in seen["user"]
    assert unquote(m.sources[0]) == "https://ko.wikisource.org/wiki/운수_좋은_날"
    assert unquote(m.sources[1]) == "https://ko.wikipedia.org/wiki/운수_좋은_날"
    assert m.markdown == "## 작품 정보\n현진건" and m.warnings == []

def test_copyrighted_work_has_no_original():
    m = fetch_literature("운수 좋은 날", llm=lambda s, u, **k: "노트", get_json=fake_get_json(source=False))
    assert m.original is None and "저작권" in m.warnings[0]

def test_nothing_found():
    with pytest.raises(OfficeError, match="작가"):
        fetch_literature("없는작품", llm=lambda s, u, **k: "", get_json=fake_get_json(False, False))
