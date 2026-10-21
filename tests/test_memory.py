import json

from office.memory import Memory


def test_remember_dedupes_and_persists(tmp_path):
    m = Memory(tmp_path / "memory.json")
    a = m.add(" 대표님은 고2, 이과 ")
    assert m.add("대표님은 고2,  이과") == a  # 같은 기억은 하나만
    m.add("수학 학원은 매주 화요일 6시")
    again = Memory(tmp_path / "memory.json")
    assert [f["text"] for f in again.facts()] == ["수학 학원은 매주 화요일 6시", "대표님은 고2, 이과"]
    assert "매주 화요일" in again.prompt()


def test_forget_by_words_or_id(tmp_path):
    m = Memory(tmp_path / "memory.json")
    a = m.add("영어 단어는 아침에 외운다")
    m.add("좋아하는 과목은 과학")
    assert [f["text"] for f in m.forget("과학")] == ["좋아하는 과목은 과학"]
    assert [f["text"] for f in m.forget(a["id"])] == ["영어 단어는 아침에 외운다"] and m.facts() == []
    assert m.forget("없는 기억") == []


def test_limits(tmp_path):
    m = Memory(tmp_path / "memory.json")
    for i in range(250):
        m.add(f"기억 {i}")
    assert len(m.facts()) == 200 and m.facts()[0]["text"] == "기억 249"  # 오래된 것부터 밀려난다
    assert len(m.prompt(limit=300)) <= 300
    assert len(m.add("가" * 1000)["text"]) == 300
