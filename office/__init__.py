from dataclasses import dataclass, field
from pathlib import Path

TEMPLATES = Path(__file__).parent / "templates"


class OfficeError(Exception):
    """화면에 그대로 보여줄 한국어 메시지."""


@dataclass
class Material:
    title: str
    markdown: str
    sources: list[str] = field(default_factory=list)
    original: str | None = None
    warnings: list[str] = field(default_factory=list)


def fill(name: str, **values: str) -> str:
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(f"__{key.upper()}__", value)
    return text


def quiet(msg: str) -> None:
    pass
