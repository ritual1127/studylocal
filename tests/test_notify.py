import json
import xml.dom.minidom
import pytest
from office import OfficeError
from office.notify import Notifier, toast_xml


def make(tmp_path, **kw):
    calls = {"run": [], "post": []}
    n = Notifier(tmp_path / "settings.json", run=lambda cmd, **k: calls["run"].append((cmd, k)),
                 post=lambda url, payload: calls["post"].append((url, payload)), register=lambda: None, **kw)
    return n, calls


def test_toast_xml_escapes_and_parses():
    doc = toast_xml("<b>&\"수학\"", "</text><script>")
    assert "&lt;b&gt;&amp;" in doc and "<script>" not in doc
    xml.dom.minidom.parseString(doc)


def test_pc_only_by_default(tmp_path):
    n, calls = make(tmp_path)
    assert n.send("제목", "내용") == []
    assert len(calls["run"]) == 1 and calls["post"] == []
    cmd, kw = calls["run"][0]
    assert cmd[0] == "powershell" and "제목" in kw["env"]["RITUAL_TOAST"]


def test_phone_on_creates_secret_topic_and_persists(tmp_path):
    n, calls = make(tmp_path)
    s = n.update({"phone": True})
    assert s["topic"].startswith("ritual-") and len(s["topic"]) >= 20
    n.send("시험", "내일 수학")
    url, payload = calls["post"][0]
    assert url == "https://ntfy.sh" and payload["topic"] == s["topic"] and payload["title"] == "시험"
    again, _ = make(tmp_path)
    assert again.settings["topic"] == s["topic"] and again.settings["phone"] is True


def test_bad_settings_rejected(tmp_path):
    n, _ = make(tmp_path)
    for bad in ({"server": "ftp://x"}, {"briefing": "25:99"}, {"pc": "yes"}):
        with pytest.raises(OfficeError):
            n.update(bad)
    assert n.update({"briefing": ""})["briefing"] == ""


def test_channel_error_is_reported_not_raised(tmp_path):
    def broken(url, payload):
        raise OfficeError("인터넷 연결을 확인해줘.")
    n = Notifier(tmp_path / "s.json", run=lambda cmd, **k: None, post=broken, register=lambda: None)
    n.update({"phone": True, "pc": False})
    assert n.send("a", "b") == ["폰: 인터넷 연결을 확인해줘."]
    assert n.history[0]["title"] == "a" and n.history[0]["errors"]


def test_ai_mode_setting(tmp_path):
    n, _ = make(tmp_path)
    assert n.settings["ai"] == "fast" and n.update({"ai": "careful"})["ai"] == "careful"
    with pytest.raises(OfficeError):
        n.update({"ai": "turbo"})


def test_phone_posts_json_to_server_root_even_if_topic_url_was_saved(tmp_path):
    # 주제 주소(https://ntfy.sh/주제)로 JSON을 보내면 ntfy가 JSON을 글자 그대로 알림에 띄운다 → 늘 서버 루트로
    (tmp_path / "settings.json").write_text(json.dumps({"phone": True, "topic": "ritual-abc", "server": "https://ntfy.sh/ritual-abc"}),
                                            encoding="utf-8")
    n, calls = make(tmp_path)
    assert n.settings["server"] == "https://ntfy.sh"
    n.send("결재 요청", "본문")
    url, payload = calls["post"][0]
    assert url == "https://ntfy.sh" and payload["topic"] == "ritual-abc" and payload["title"] == "결재 요청"
    assert n.update({"server": "https://ntfy.example.com/some-topic/"})["server"] == "https://ntfy.example.com"
