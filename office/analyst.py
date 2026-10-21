"""분석가: 어떤 자료든 학생 눈높이의 분석 보고서로 (종류·과목·난이도, 요약, 핵심 개념, 시험 포인트, 공부법)."""
import html
import json
from pathlib import Path

from office import Material, OfficeError, fill, quiet
from office.config import GALMURI_CSS
from office.llm import chat_json, clip
from office.note import with_feedback

_LIST = {"type": "array", "items": {"type": "string"}}
ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"}, "kind": {"type": "string"}, "subject": {"type": "string"},
        "level": {"type": "integer"}, "one_line": {"type": "string"}, "summary": _LIST,
        "concepts": {"type": "array", "items": {
            "type": "object", "properties": {"term": {"type": "string"}, "why": {"type": "string"}},
            "required": ["term", "why"]}},
        "exam_points": _LIST, "pitfalls": _LIST, "study_tips": _LIST, "minutes": {"type": "integer"},
    },
    "required": ["title", "kind", "subject", "level", "one_line", "summary", "concepts", "exam_points", "pitfalls",
                 "study_tips", "minutes"],
}

ANALYST_SYSTEM = """너는 '공부 사무실'의 분석가 직원이다. 어떤 종류의 자료든 학생 입장에서 분석해 보고서를 쓴다.
- kind: 자료 종류(예: 수업 프린트, 시험지, 교과서, 문학 작품, 기사, 발표 자료, 데이터 표, 코드)
- subject: 과목(국어·영어·수학·과학·사회·역사·정보·기타 중 하나), level: 난이도 1~5
- one_line: 한 줄 요약, summary: 핵심 내용 3~6줄
- concepts: 꼭 알아야 할 개념과 왜 중요한지(why), exam_points: 시험에 나올 만한 것, pitfalls: 헷갈리기 쉬운 것
- study_tips: 이 자료를 공부하는 방법 2~4개, minutes: 다 익히는 데 걸릴 예상 공부 시간(분)
데이터 표라면 눈에 띄는 경향·가장 큰 값·가장 작은 값을 짚는다. 자료에 없는 사실은 지어내지 않는다. JSON으로만 답한다."""


def _text(value, limit: int = 200) -> str:
    return " ".join(value.split())[:limit] if isinstance(value, str) else ""


def _strings(values, limit: int = 8) -> list[str]:
    return [t for t in (_text(v) for v in (values if isinstance(values, list) else [])) if t][:limit]


def _int(value, default: int, low: int, high: int) -> int:
    return max(low, min(high, value)) if isinstance(value, int) and not isinstance(value, bool) else default


def validate_analysis(raw: dict) -> dict:
    concepts = [{"term": _text(c.get("term"), 60), "why": _text(c.get("why"))}
                for c in raw.get("concepts") or [] if isinstance(c, dict) and _text(c.get("term"))][:10]
    report = {"title": _text(raw.get("title"), 60), "kind": _text(raw.get("kind"), 30) or "자료",
              "subject": _text(raw.get("subject"), 20) or "기타", "level": _int(raw.get("level"), 3, 1, 5),
              "one_line": _text(raw.get("one_line")), "summary": _strings(raw.get("summary")), "concepts": concepts,
              "exam_points": _strings(raw.get("exam_points")), "pitfalls": _strings(raw.get("pitfalls")),
              "study_tips": _strings(raw.get("study_tips"), 5), "minutes": _int(raw.get("minutes"), 30, 5, 600)}
    if not report["one_line"] and not report["summary"]:
        raise OfficeError("분석할 내용을 못 찾았어. 다시 시도해줘.")
    return report


def make_analysis_page(material: Material, job_dir: Path, llm=chat_json, say=quiet, feedback: str = "") -> Path:
    say("자료 분석하는 중")
    report = validate_analysis(llm(ANALYST_SYSTEM, with_feedback(clip(material.markdown), feedback), ANALYSIS_SCHEMA,
                                   temperature=0.2))
    report["title"] = report["title"] or material.title
    folder = Path(job_dir) / "analysis"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    page = folder / "index.html"
    page.write_text(fill("analysis.html", title=html.escape(report["title"]), galmuri_css=GALMURI_CSS,
                         report_json=json.dumps(report, ensure_ascii=False).replace("<", "\\u003c")), encoding="utf-8")
    say(f"{report['kind']} · {report['subject']} · 난이도 {report['level']}")
    return page
