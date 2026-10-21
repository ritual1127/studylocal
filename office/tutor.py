"""선생님: 질문에 답한다. 자료가 있으면 자료를 근거로."""
from pathlib import Path

from office import Material, OfficeError, quiet
from office.llm import chat, clip

TUTOR_SYSTEM = """너는 '공부 사무실'의 선생님 직원이다. 학생의 질문에 친절한 반말로, 이해하기 쉽게 답한다.
자료가 주어지면 자료를 근거로 답하고, 자료에 없는 내용은 "자료에는 없지만"이라고 밝힌다.
핵심부터 말하고, 필요하면 짧은 예시를 든다. 마크다운(굵게, 목록)을 써도 된다. 모르면 모른다고 한다."""


def answer_question(question: str, material: Material | None, job_dir: Path, llm=chat, say=quiet,
                    feedback: str = "") -> Path:
    say("답 생각하는 중")
    parts = [f"질문: {question}"]
    if material:
        parts.append(f"[자료: {material.title}]\n{clip(material.markdown)}")
    if feedback:
        parts.append(f"[대표 수정 요청] {feedback}")
    text = llm(TUTOR_SYSTEM, "\n\n".join(parts), temperature=0.3).strip()
    if not text:
        raise OfficeError("답을 못 만들었어. 다시 물어봐줘.")
    path = Path(job_dir) / "answer.md"
    path.write_text(text, encoding="utf-8")
    return path
