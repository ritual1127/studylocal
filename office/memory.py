"""실장님의 기억: 대표님에 대해 알아 둘 것. 매번 대화 맨 앞에 넣어서 계속 알고 있게 한다."""
import datetime as dt
import json
import re
import secrets
import threading
from pathlib import Path

from office import OfficeError

MAX_FACTS = 200
MAX_CHARS = 300


def _key(text: str) -> str:
    return re.sub(r"\s+", "", text)


class Memory:
    def __init__(self, path: Path, now=dt.datetime.now):
        self.path, self.now = Path(path), now
        self.lock = threading.Lock()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        facts = data.get("facts") if isinstance(data, dict) else None
        self._facts = [f for f in facts or [] if isinstance(f, dict) and isinstance(f.get("text"), str) and f.get("id")]

    def _save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"facts": self._facts}, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def facts(self) -> list[dict]:
        """새것부터."""
        with self.lock:
            return [dict(f) for f in reversed(self._facts)]

    def add(self, text: str) -> dict:
        text = " ".join(str(text or "").split())[:MAX_CHARS]
        if not text:
            raise OfficeError("기억할 내용을 알려 주세요.")
        with self.lock:
            same = next((f for f in self._facts if _key(f["text"]) == _key(text)), None)
            if same:
                return dict(same)
            fact = {"id": secrets.token_hex(4), "text": text, "created": f"{self.now():%Y-%m-%d %H:%M}"}
            self._facts.append(fact)
            del self._facts[:-MAX_FACTS]  # ponytail: 200개 넘으면 오래된 것부터 밀어낸다
            self._save()
            return dict(fact)

    def forget(self, query: str) -> list[dict]:
        """작업 번호 같은 id나, 그 말이 들어간 기억을 지운다."""
        query = str(query or "").strip()
        if not query:
            return []
        with self.lock:
            gone = [f for f in self._facts if f["id"] == query or _key(query) in _key(f["text"])]
            if gone:
                self._facts = [f for f in self._facts if f not in gone]
                self._save()
            return [dict(f) for f in gone]

    def prompt(self, limit: int = 2000) -> str:
        """대화 맨 앞에 넣을 글 (새 기억부터, limit 글자 안에서)."""
        lines, size = [], 0
        for f in self.facts():
            line = f"- {f['text']}"
            if size + len(line) + 1 > limit:
                break
            lines.append(line)
            size += len(line) + 1
        return "\n".join(lines)
