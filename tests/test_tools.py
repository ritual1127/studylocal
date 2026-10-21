import datetime
import os
import time
import zipfile

import pytest

from office import OfficeError
from office.tools import Files


@pytest.fixture
def home(tmp_path):
    for name in ("Desktop", "Documents", "Downloads", "AppData/Roaming", ".ssh", "Desktop/node_modules/pkg"):
        (tmp_path / name).mkdir(parents=True)
    (tmp_path / "Desktop" / "수학_2학기_프린트.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "Desktop" / "영어 단어.txt").write_text("apple 사과", encoding="utf-8")
    (tmp_path / "Downloads" / "수학 숙제.hwp").write_bytes(b"x")
    (tmp_path / "Desktop" / "node_modules" / "pkg" / "수학.js").write_text("x", encoding="utf-8")
    (tmp_path / ".ssh" / "id_rsa").write_text("secret", encoding="utf-8")
    (tmp_path / "AppData" / "Roaming" / "수학.txt").write_text("x", encoding="utf-8")
    old = tmp_path / "Downloads" / "옛날 수학.pdf"
    old.write_bytes(b"%PDF")
    stamp = time.time() - 40 * 86400
    os.utime(old, (stamp, stamp))
    return tmp_path


def files(home, **perms):
    folders = {"Desktop": home / "Desktop", "Documents": home / "Documents", "Downloads": home / "Downloads"}
    return Files(roots=[home], folders=folders, perms={"read": True, "write": True, "risky": True, "command": True, **perms})


def test_resolve_aliases_and_blocks_escapes(home):
    f = files(home)
    assert f.resolve("바탕화면/영어 단어.txt") == home / "Desktop" / "영어 단어.txt"
    assert f.resolve("다운로드") == home / "Downloads"
    for bad in ("../outside.txt", str(home.parent), "~/.ssh/id_rsa", ".ssh/id_rsa", "AppData/Roaming/수학.txt"):
        with pytest.raises(OfficeError):
            f.resolve(bad)


def test_find_by_words_kind_and_days_skips_hidden_places(home):
    f = files(home)
    names = [r["name"] for r in f.find("수학")]
    assert set(names) == {"수학_2학기_프린트.pdf", "수학 숙제.hwp", "옛날 수학.pdf"}  # node_modules·AppData·.ssh는 안 뒤짐
    assert [r["name"] for r in f.find("수학 프린트")] == ["수학_2학기_프린트.pdf"]
    assert [r["name"] for r in f.find("수학", kind="한글")] == ["수학 숙제.hwp"]
    assert "옛날 수학.pdf" not in [r["name"] for r in f.find("수학", days=30)]
    assert [r["name"] for r in f.find("수학", folder="다운로드")] == ["수학 숙제.hwp", "옛날 수학.pdf"]


def test_list_and_read(home):
    f = files(home)
    listing = f.listing("바탕화면")
    assert {"영어 단어.txt", "수학_2학기_프린트.pdf"} <= {e["name"] for e in listing["files"]} and "node_modules" in listing["folders"]
    assert f.read_text(f.resolve("바탕화면/영어 단어.txt")) == "apple 사과"
    with pytest.raises(OfficeError, match="읽기"):
        files(home, read=False).find("수학")


def test_write_never_overwrites_without_approval(home):
    f = files(home)
    p1 = f.write("메모.txt", "첫 번째")
    p2 = f.write("메모.txt", "두 번째")
    assert p1.parent == home / "Documents" / "ritual's rab" and p2.name == "메모 (2).txt"
    assert p1.read_text(encoding="utf-8") == "첫 번째" and p2.read_text(encoding="utf-8") == "두 번째"
    with pytest.raises(OfficeError, match="만들기"):
        files(home, write=False).write("x.txt", "x")


def test_copy_move_rename_delete_and_folder(home):
    trashed = []
    f = files(home)
    f.trash = trashed.append
    src = home / "Downloads" / "수학 숙제.hwp"
    copied = f.copy(src, f.resolve("바탕화면"))
    assert copied.exists() and src.exists()
    moved = f.move(copied, f.resolve("문서"))
    assert moved == home / "Documents" / "수학 숙제.hwp" and not copied.exists()
    renamed = f.rename(moved, "수학 숙제 1.hwp")
    assert renamed.name == "수학 숙제 1.hwp"
    with pytest.raises(OfficeError):
        f.rename(renamed, "../밖으로.hwp")
    f.delete(renamed)
    assert trashed == [renamed]
    assert f.make_folder("문서/새 폴더").is_dir()


def test_risky_need_risky_permission(home):
    with pytest.raises(OfficeError, match="권한"):
        files(home, risky=False).delete(home / "Downloads" / "수학 숙제.hwp")
