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
