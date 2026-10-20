import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from office import Material, OfficeError, quiet
from office.llm import chat, clip

WIKISOURCE = "ko.wikisource.org"
WIKIPEDIA = "ko.wikipedia.org"
UA = "RitualStudyOffice/0.1 (personal study tool)"

SKIP_CLASSES = {"ws-noexport", "noprint", "mw-editsection", "licenseContainer", "licensetpl"}
SKIP_TAGS = {"style", "script"}
BLOCK_TAGS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "dd", "dt"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

LIB_SYSTEM = """너는 '공부 사무실'의 사서 직원이다. 주어진 자료만 근거로 학생용 문학 공부 노트를 마크다운으로 쓴다.
항목: ## 작품 정보(작가·갈래·시대), ## 내용 정리, ## 주제, ## 표현상 특징, ## 감상 포인트
자료에 없는 내용은 지어내지 말고 "자료에 없음"이라고 쓴다. 노트만 출력한다."""


def _get_json(host: str, params: dict) -> dict:
    query = urllib.parse.urlencode({**params, "format": "json", "formatversion": 2})
    req = urllib.request.Request(f"https://{host}/w/api.php?{query}", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)
    except (OSError, ValueError) as e:
        raise OfficeError("인터넷 연결을 확인해줘. (위키 접속 실패)") from e


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        void = tag in VOID_TAGS
        if self.skip_depth:
            if not void:
                self.skip_depth += 1
            return
        classes = set((dict(attrs).get("class") or "").split())
        if tag in SKIP_TAGS or classes & SKIP_CLASSES:
            if not void:
                self.skip_depth = 1
            return
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.skip_depth:
            if tag not in VOID_TAGS:
                self.skip_depth -= 1
            return
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextParser()
    parser.feed(html)
    parser.close()
    lines = [line.strip() for line in "".join(parser.parts).splitlines()]
    lines = [line if any(ch.isalnum() for ch in line) else "" for line in lines]  # 장식 기호 줄 버림
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text.removesuffix("라이선스").rstrip()  # 위키문헌 라이선스 틀 제목


def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def pick_title(query: str, titles: list[str]) -> str | None:
    q = _norm(query)
    for title in titles:
        t = _norm(title)
        if q and (q in t or (len(t) >= 2 and t in q)):
            return title
    return None


def page_url(host: str, title: str) -> str:
    return f"https://{host}/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"


def _search(get_json, host: str, query: str) -> list[str]:
    data = get_json(host, {"action": "query", "list": "search", "srsearch": query, "srlimit": 5})
    return [hit["title"] for hit in data.get("query", {}).get("search", [])]


def fetch_literature(query: str, llm=chat, get_json=_get_json, say=quiet) -> Material:
    say("위키문헌에서 원문 찾는 중")
    source_title = pick_title(query, _search(get_json, WIKISOURCE, query))
    original = None
    if source_title:
        data = get_json(WIKISOURCE, {"action": "parse", "page": source_title, "prop": "text", "redirects": 1})
        original = html_to_text(data["parse"]["text"]) or None

    say("위키백과에서 해설 자료 찾는 중")
    wiki_title = pick_title(query, _search(get_json, WIKIPEDIA, query))
    info = ""
    if wiki_title:
        data = get_json(WIKIPEDIA, {"action": "query", "prop": "extracts", "explaintext": 1,
                                    "redirects": 1, "titles": wiki_title})
        pages = data.get("query", {}).get("pages", [])
        info = (pages[0].get("extract") or "") if pages else ""

    if not original and not info:
        raise OfficeError(f"'{query}'을(를) 못 찾았어. 작가 이름도 같이 써줘.")

    title = source_title or wiki_title
    say("공부 노트 쓰는 중")
    user = (f"작품: {title}\n\n[해설 자료]\n{clip(info, 4000) or '(해설 자료 없음)'}\n\n"
            f"[원문 앞부분]\n{clip(original, 4000) if original else '(원문 없음: 저작권 보호 작품일 수 있음)'}")
    note = llm(LIB_SYSTEM, user, temperature=0.2).strip()
    sources = [page_url(WIKISOURCE, source_title)] if source_title else []
    if wiki_title:
        sources.append(page_url(WIKIPEDIA, wiki_title))
    warnings = [] if original else ["위키문헌에 원문이 없어(저작권 보호 작품일 수 있음) 해설만 정리했어."]
    return Material(title=title, markdown=note, sources=sources, original=original, warnings=warnings)
