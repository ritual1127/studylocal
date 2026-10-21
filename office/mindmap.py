"""정리왕: 자료를 한 장짜리 개념 마인드맵으로."""
import html
import json
from pathlib import Path

from office import Material, OfficeError, fill, quiet
from office.config import GALMURI_CSS
from office.llm import chat_json, clip

MAX_BRANCHES, MAX_CHILDREN, MAX_DETAILS = 8, 6, 3

MINDMAP_SCHEMA = {
    "type": "object",
    "properties": {
        "center": {"type": "string"},
        "branches": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "label": {"type": "string"},
                "children": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"label": {"type": "string"},
                                   "details": {"type": "array", "items": {"type": "string"}}},
                    "required": ["label", "details"]}}},
            "required": ["label", "children"]}},
    },
    "required": ["center", "branches"],
}

MINDMAP_SYSTEM = """너는 '공부 사무실'의 정리왕 직원이다. 자료 전체를 한눈에 보는 마인드맵으로 정리한다.
center는 주제, branches는 큰 갈래 4~7개, 각 갈래의 children은 핵심 개념 2~5개, details는 아주 짧은 설명 0~2개.
모든 글은 짧게(15자 안팎). 자료에 없는 내용은 넣지 않는다. JSON으로만 답한다."""


def _label(value, limit: int = 40) -> str:
    return " ".join(str(value or "").split())[:limit]


def validate_mindmap(raw: dict) -> dict:
    branches = []
    for branch in raw.get("branches") or []:
        if not isinstance(branch, dict) or not _label(branch.get("label")):
            continue
        children = []
        for child in branch.get("children") or []:
            if isinstance(child, dict) and _label(child.get("label")):
                details = [_label(d, 60) for d in child.get("details") or [] if _label(d, 60)][:MAX_DETAILS]
                children.append({"label": _label(child["label"]), "details": details})
        branches.append({"label": _label(branch["label"]), "children": children[:MAX_CHILDREN]})
    if len(branches) < 2:
        raise OfficeError("마인드맵 갈래가 너무 적어. 다시 시도해줘.")
    return {"center": _label(raw.get("center")) or "주제", "branches": branches[:MAX_BRANCHES]}


def make_mindmap_page(material: Material, job_dir: Path, llm=chat_json, say=quiet, feedback: str = "") -> Path:
    say("마인드맵 그리는 중")
    user = clip(material.markdown)
    if feedback:
        user += f"\n\n[대표 수정 요청] {feedback}"
    tree = validate_mindmap(llm(MINDMAP_SYSTEM, user, MINDMAP_SCHEMA, temperature=0.2))
    folder = Path(job_dir) / "mindmap"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "mindmap.json").write_text(json.dumps(tree, ensure_ascii=False, indent=1), encoding="utf-8")
    page = folder / "index.html"
    page.write_text(fill("mindmap.html", title=html.escape(tree["center"]), galmuri_css=GALMURI_CSS,
                         tree_json=json.dumps(tree, ensure_ascii=False).replace("<", "\\u003c")), encoding="utf-8")
    say(f"갈래 {len(tree['branches'])}개로 정리했어")
    return page
