import base64
import html
import json
from pathlib import Path

from office import Material, OfficeError, fill, quiet
from office.config import GALMURI_CSS, WEB
from office.llm import chat_json, clip
from office.note import with_feedback

QUIZ_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "questions": {"type": "array", "items": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": ["mc", "ox", "short"]},
                           "question": {"type": "string"},
                           "choices": {"type": "array", "items": {"type": "string"}},
                           "answer": {"type": "string"},
                           "explanation": {"type": "string"}},
            "required": ["kind", "question", "choices", "answer", "explanation"]}},
    },
    "required": ["title", "questions"],
}

QUIZ_SYSTEM = """너는 '공부 사무실'의 출제위원 직원이다. 주어진 자료의 내용으로만 문제를 낸다.
- mc(객관식): choices에 보기 4개, answer에는 정답 보기 문장을 그대로 쓴다
- ox: choices는 빈 배열, answer는 O 또는 X
- short(단답): choices는 빈 배열, answer는 짧은 정답
모든 문제에 explanation(해설)을 쓴다. 자료에 없는 사실은 묻지 않는다. 객관식 위주로 섞는다.
title에는 문제 세트의 짧은 제목을 쓴다. JSON으로만 답한다."""

MC_MARKS = {"①": 0, "②": 1, "③": 2, "④": 3}
OX_O = {"o", "○", "⭕", "참", "맞음", "true"}
OX_X = {"x", "×", "❌", "거짓", "틀림", "false"}


def _mc_answer(answer: str, choices: list[str]) -> int | None:
    if answer in choices:
        return choices.index(answer)
    if answer in {"1", "2", "3", "4"}:
        return int(answer) - 1
    if answer in MC_MARKS:
        return MC_MARKS[answer]
    if answer.upper() in {"A", "B", "C", "D"}:
        return "ABCD".index(answer.upper())
    return None


def validate_quiz(raw: dict) -> dict:
    seen, questions = set(), []
    for q in raw.get("questions") or []:
        if not isinstance(q, dict):
            continue
        text = str(q.get("question") or "").strip()
        if not text or text in seen:
            continue
        answer = str(q.get("answer") or "").strip()
        item = {"kind": q.get("kind"), "question": text, "choices": [],
                "explanation": str(q.get("explanation") or "").strip()}
        if item["kind"] == "mc":
            choices = [str(c).strip() for c in q.get("choices") or []]
            index = _mc_answer(answer, choices) if len(choices) == 4 and all(choices) else None
            if index is None:
                continue
            item.update(choices=choices, answer=index)
        elif item["kind"] == "ox":
            low = answer.lower()
            if low not in OX_O | OX_X:
                continue
            item["answer"] = "O" if low in OX_O else "X"
        elif item["kind"] == "short" and answer:
            item["answer"] = answer
        else:
            continue
        seen.add(text)
        questions.append(item)
    if len(questions) < 3:
        raise OfficeError("쓸 만한 문제가 3개도 안 나왔어. 다시 시도해줘.")
    return {"title": str(raw.get("title") or "").strip() or "문제", "questions": questions}


def make_quiz(material: Material, count: int, llm=chat_json, feedback: str = "") -> dict:
    source = material.markdown + (f"\n\n[원문]\n{material.original}" if material.original else "")
    user = with_feedback(f"문제 수: {count}\n\n{clip(source)}", feedback)
    try:
        quiz = validate_quiz(llm(QUIZ_SYSTEM, user, QUIZ_SCHEMA, temperature=0.3))
    except OfficeError:
        quiz = validate_quiz(llm(QUIZ_SYSTEM, user, QUIZ_SCHEMA, temperature=0.3))
    quiz["questions"] = quiz["questions"][:count]
    return quiz


def render_quiz_html(quiz: dict) -> str:
    logo = WEB / "logo-pixel.png"
    logo_html = (f'<img class="logo" alt="ritual" src="data:image/png;base64,'
                 f'{base64.b64encode(logo.read_bytes()).decode()}">') if logo.exists() else '<b class="logo-text">ritual</b>'
    return fill("quiz.html", title=html.escape(quiz["title"]), logo=logo_html, galmuri_css=GALMURI_CSS,
                quiz_json=json.dumps(quiz, ensure_ascii=False).replace("<", "\\u003c"))


def save_quiz(job_dir: Path, quiz: dict) -> Path:
    folder = job_dir / "quiz"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "quiz.json").write_text(json.dumps(quiz, ensure_ascii=False, indent=1), encoding="utf-8")
    index = folder / "index.html"
    index.write_text(render_quiz_html(quiz), encoding="utf-8")
    return index


def make_quiz_page(material: Material, count: int, job_dir: Path, llm=chat_json, say=quiet,
                   feedback: str = "") -> Path:
    say(f"문제 {count}개 내는 중")
    quiz = make_quiz(material, count, llm=llm, feedback=feedback)
    say(f"{len(quiz['questions'])}문제 완성")
    return save_quiz(job_dir, quiz)
