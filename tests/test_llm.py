import base64, io, urllib.error
import pytest
from office import OfficeError
from office import llm

def test_chat_down_raises_korean_hint(monkeypatch):
    monkeypatch.setattr(llm, "OLLAMA_URL", "http://127.0.0.1:9")
    with pytest.raises(OfficeError, match="Ollama"):
        llm.chat("s", "u")

def test_missing_model_hint(monkeypatch):
    def fake_post(path, payload, timeout):
        raise urllib.error.HTTPError("x", 404, "not found", None, io.BytesIO(b'{"error":"model not found"}'))
    monkeypatch.setattr(llm, "_post", fake_post)
    with pytest.raises(OfficeError, match="ollama pull"):
        llm.chat("s", "u")

def test_chat_sends_images_schema_and_no_think(monkeypatch):
    seen = {}
    def fake_post(path, payload, timeout):
        seen.update(path=path, payload=payload)
        return {"message": {"content": "안녕"}}
    monkeypatch.setattr(llm, "_post", fake_post)
    assert llm.chat("sys", "hi", images=[b"\x89PNG"], schema={"type": "object"}) == "안녕"
    p = seen["payload"]
    assert seen["path"] == "/api/chat"
    assert p["messages"][0] == {"role": "system", "content": "sys"}
    assert p["messages"][1]["images"] == [base64.b64encode(b"\x89PNG").decode()]
    assert p["format"] == {"type": "object"} and p["think"] is False and p["stream"] is False
    assert p["options"]["num_ctx"] == 16384 and p["keep_alive"] == "10m"

def test_chat_json_retries_once_then_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "_post", lambda path, payload, timeout: calls.append(1) or {"message": {"content": "{깨진"}})
    with pytest.raises(OfficeError, match="형식"):
        llm.chat_json("s", "u", {"type": "object"})
    assert len(calls) == 2

def test_chat_json_recovers_on_retry(monkeypatch):
    replies = iter(["{깨진", '{"ok": true}'])
    monkeypatch.setattr(llm, "_post", lambda path, payload, timeout: {"message": {"content": next(replies)}})
    assert llm.chat_json("s", "u", {"type": "object"}) == {"ok": True}

def test_clip():
    assert llm.clip("가나다", 10) == "가나다"
    assert llm.clip("가" * 12, 10) == "가" * 10 + "\n\n(이하 생략)"
