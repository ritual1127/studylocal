from office import startup


def test_turn_on_makes_hidden_startup_shortcut_via_env(tmp_path):
    calls = []
    lnk = tmp_path / "Startup" / "office.lnk"
    lnk.parent.mkdir()
    assert startup.set_enabled(True, path=lnk, run=lambda cmd, **kw: calls.append((cmd, kw)) or lnk.write_bytes(b"lnk")) is True
    cmd, kw = calls[0]
    assert cmd[0] == "powershell" and kw["env"]["RITUAL_LNK"] == str(lnk)
    assert kw["env"]["RITUAL_ARGS"].endswith("--background") and kw["env"]["RITUAL_TARGET"].lower().endswith("pythonw.exe")
    assert "RITUAL_LNK" not in " ".join(cmd[1:-1])  # 경로는 명령어가 아니라 환경 변수로만 넘긴다
    assert startup.is_enabled(lnk)


def test_turn_off_removes_shortcut(tmp_path):
    lnk = tmp_path / "office.lnk"
    lnk.write_bytes(b"lnk")
    assert startup.set_enabled(False, path=lnk, run=None) is False and not lnk.exists()
    assert startup.set_enabled(False, path=lnk, run=None) is False  # 이미 없어도 괜찮다
