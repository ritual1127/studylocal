"""rab의 손발: 대표 PC의 허용 폴더 안에서만 파일을 찾고·읽고·가져오고·새로 만든다.

허용 폴더 밖, AppData·.ssh 같은 곳은 늘 막는다. 지우기·옮기기·덮어쓰기·명령 실행은 rab에게 없다 (대표가 직접).
"""
import datetime as dt
import json
import os
import re
import shutil
from pathlib import Path

from office import OfficeError

# 말로 부르는 폴더 이름 → 알려진 폴더 키
ALIASES = {"바탕화면": "Desktop", "바탕 화면": "Desktop", "desktop": "Desktop", "문서": "Documents", "내 문서": "Documents",
           "documents": "Documents", "다운로드": "Downloads", "downloads": "Downloads", "사진": "Pictures", "그림": "Pictures",
           "pictures": "Pictures", "음악": "Music", "music": "Music", "동영상": "Videos", "비디오": "Videos", "videos": "Videos",
           "원드라이브": "OneDrive", "onedrive": "OneDrive"}
KNOWN = {"Desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641", "Documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
         "Downloads": "374DE290-123F-4565-9164-39C4925E467B", "Pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
         "Music": "4BD8D571-6D19-48D3-BE97-422220080E43", "Videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC"}
BLOCKED = {"appdata", ".ssh", ".gnupg", ".aws", ".azure", ".kube", "$recycle.bin", "windows", "program files",
           "program files (x86)", "programdata"}
SKIP = BLOCKED | {".git", "node_modules", "__pycache__", ".venv", "venv", ".cache", ".idea", ".vscode"}
KINDS = {"pdf": {".pdf"}, "한글": {".hwp", ".hwpx"}, "워드": {".docx", ".doc"}, "엑셀": {".xlsx", ".xls", ".csv"},
         "ppt": {".pptx", ".ppt"}, "사진": {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".heic"},
         "영상": {".mp4", ".mov", ".avi", ".mkv"}, "음악": {".mp3", ".wav", ".m4a", ".flac"},
         "글자": {".txt", ".md", ".csv", ".json"}}
KINDS["문서"] = KINDS["pdf"] | KINDS["한글"] | KINDS["워드"] | KINDS["ppt"] | KINDS["글자"] | {".xlsx"}
KINDS.update({"이미지": KINDS["사진"], "그림": KINDS["사진"], "동영상": KINDS["영상"], "hwp": KINDS["한글"], "docx": KINDS["워드"],
              "xlsx": KINDS["엑셀"], "pptx": KINDS["ppt"], "파워포인트": KINDS["ppt"], "텍스트": KINDS["글자"]})
MAX_SCAN, MAX_SECONDS = 200_000, 5.0
PERM_NAMES = {"read": "파일 읽기", "write": "파일 만들기·가져오기"}
def known_folder(key: str) -> Path | None:
    """Windows가 아는 진짜 위치 (OneDrive로 옮긴 바탕화면도)."""
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]
        u = uuid.UUID(KNOWN[key])
        guid = GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8)(*u.bytes[8:]))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) != 0:
            return None
        path = out.value
        ctypes.windll.ole32.CoTaskMemFree(ctypes.cast(out, ctypes.c_void_p))
        return Path(path)
    except (OSError, AttributeError, KeyError, ValueError):
        return None


def default_folders() -> dict[str, Path]:
    folders = {}
    for key in KNOWN:
        path = known_folder(key) or Path.home() / key
        if path.exists():
            folders[key] = path
    if os.environ.get("OneDrive") and Path(os.environ["OneDrive"]).exists():
        folders["OneDrive"] = Path(os.environ["OneDrive"])
    return folders


def _norm(text: str) -> str:
    return re.sub(r"[\s_\-.()\[\]]+", "", text.lower())


def _free_name(folder: Path, name: str) -> Path:
    target = folder / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 2
    while target.exists():
        target = folder / f"{stem} ({n}){suffix}"
        n += 1
    return target


class Files:
    """허용 폴더(roots) 안에서만 동작하는 파일 도구. perms: read · write 켜기/끄기."""

    def __init__(self, roots: list[Path], folders: dict[str, Path], perms: dict):
        self.roots = [Path(r).resolve() for r in roots]
        self.folders = {k: Path(v) for k, v in folders.items()}
        self.perms = perms

    def need(self, perm: str) -> None:
        if not self.perms.get(perm):
            raise OfficeError(f"'{PERM_NAMES[perm]}' 권한이 꺼져 있어요. 설정 → rab 권한에서 켜 주세요.")

    def allowed(self, path: Path) -> bool:
        path = Path(path).resolve()
        for root in self.roots:
            if path == root or path.is_relative_to(root):  # 허용 폴더 아래쪽에 AppData·.ssh 같은 게 끼면 막는다
                return not any(part.lower() in BLOCKED for part in path.relative_to(root).parts)
        return False

    def resolve(self, text: str) -> Path:
        raw = str(text or "").strip().strip('"').replace("\\", "/")
        if not raw:
            raise OfficeError("어느 파일·폴더인지 알려 주세요.")
        head, _, rest = raw.partition("/")
        key = ALIASES.get(head.lower()) or ALIASES.get(head) or (head if head in self.folders else None)
        if key and key in self.folders:
            path = self.folders[key] / rest
        elif raw.startswith("~"):
            path = Path(raw).expanduser()
        elif Path(raw).is_absolute():
            path = Path(raw)
        else:
            path = (self.roots[0] if self.roots else Path.home()) / raw
        path = path.resolve()
        if not self.allowed(path):
            raise OfficeError(f"'{raw}'은(는) rab이 건드릴 수 있는 폴더 밖이에요. 설정 → rab 권한에서 폴더를 추가해 주세요.")
        return path

    def existing(self, text: str) -> Path:
        path = self.resolve(text)
        if not path.exists():
            raise OfficeError(f"'{text}'을(를) 못 찾았어요. 먼저 찾기로 정확한 경로를 확인할게요.")
        return path

    # ---- 읽기 ----
    def find(self, query: str = "", folder: str = "", kind: str = "", days: int = 0, limit: int = 20) -> list[dict]:
        self.need("read")
        words = [_norm(w) for w in str(query or "").split() if _norm(w)]
        exts = KINDS.get(str(kind or "").strip().lower()) or KINDS.get(str(kind or "").strip())
        since = dt.datetime.now().timestamp() - days * 86400 if days and days > 0 else 0
        starts = [self.resolve(folder)] if folder else self.roots
        found, scanned, t0 = [], 0, dt.datetime.now()
        for start in starts:
            for dirpath, dirnames, filenames in os.walk(start):
                dirnames[:] = [d for d in dirnames if d.lower() not in SKIP and not d.startswith(".")]
                for name in filenames:
                    scanned += 1
                    norm = _norm(name)
                    if words and not all(w in norm for w in words):
                        continue
                    path = Path(dirpath) / name
                    if exts and path.suffix.lower() not in exts:
                        continue
                    try:
                        stat = path.stat()
                    except OSError:
                        continue
                    if since and stat.st_mtime < since:
                        continue
                    found.append((stat.st_mtime, path, stat.st_size))
                if scanned > MAX_SCAN or (dt.datetime.now() - t0).total_seconds() > MAX_SECONDS:
                    break  # ponytail: 너무 큰 폴더는 앞부분만 (5초·20만 개), 폴더를 좁혀 달라고 하면 된다
        found.sort(key=lambda f: f[0], reverse=True)
        return [{"path": str(p), "name": p.name, "size": size,
                 "modified": dt.datetime.fromtimestamp(m).strftime("%Y-%m-%d %H:%M")} for m, p, size in found[:limit]]

    def listing(self, folder: str, limit: int = 100) -> dict:
        self.need("read")
        path = self.existing(folder)
        if not path.is_dir():
            raise OfficeError(f"'{folder}'은(는) 폴더가 아니에요.")
        entries = sorted(path.iterdir(), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
        folders = [p.name for p in entries if p.is_dir() and p.name.lower() not in BLOCKED][:limit]
        files = [{"name": p.name, "size": p.stat().st_size,
                  "modified": dt.datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")}
                 for p in entries if p.is_file()][:limit]
        return {"path": str(path), "folders": folders, "files": files}

    def read_text(self, path: Path, limit: int = 4000) -> str:
        """글자 파일·문서는 바로 (사진·스캔 PDF는 에이전트가 스캐너 직원에게 맡긴다)."""
        self.need("read")
        from office.scan import load_pages

        pages = load_pages(Path(path))
        text = "\n\n".join(p for p in pages if isinstance(p, str))
        if not text.strip():
            raise OfficeError("글자를 바로 못 읽는 파일(사진·스캔)이에요. 가져와서 스캐너 직원에게 읽힐게요.")
        return text if len(text) <= limit else text[:limit] + "\n…(이하 생략)"

    # ---- 만들기 (있는 파일은 절대 덮어쓰지 않는다) ----
    def write(self, name: str, content: str, folder: str = "") -> Path:
        self.need("write")
        target_dir = self.resolve(folder) if folder else self.folders.get("Documents", self.roots[0]) / "ritual's rab"
        clean = Path(str(name).replace("\\", "/")).name or "메모.txt"
        if not Path(clean).suffix:
            clean += ".txt"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = _free_name(target_dir, clean)  # 있는 파일은 절대 덮어쓰지 않는다
        if not self.allowed(target):
            raise OfficeError("허용 폴더 밖에는 못 써요.")
        target.write_text(str(content), encoding="utf-8")
        return target

    def copy(self, src: Path, to_folder: Path) -> Path:
        self.need("write")
        if not self.allowed(src) or not self.allowed(to_folder):
            raise OfficeError("허용 폴더 밖이에요.")
        to_folder.mkdir(parents=True, exist_ok=True)
        target = _free_name(to_folder, src.name)
        (shutil.copytree if src.is_dir() else shutil.copy2)(src, target)
        return target

    def make_folder(self, text: str) -> Path:
        self.need("write")
        path = self.resolve(text)
        path.mkdir(parents=True, exist_ok=True)
        return path

def load_permissions(path: Path) -> dict:
    """설정 → rab 권한. 기본: 알려진 폴더 전부, 읽기·만들기 켬."""
    try:
        saved = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = {}
    saved = saved if isinstance(saved, dict) else {}
    perms = {k: saved[k] if isinstance(saved.get(k), bool) else True for k in PERM_NAMES}
    extra = [p for p in saved.get("extra", []) if isinstance(p, str)] if isinstance(saved.get("extra"), list) else []
    off = [p for p in saved.get("off", []) if isinstance(p, str)] if isinstance(saved.get("off"), list) else []
    return {**perms, "extra": extra, "off": off}


def check_permissions(changes: dict, current: dict, folders: dict[str, Path]) -> dict:
    """설정 화면에서 온 값 검사. extra = 더 허용할 폴더(있는 폴더만, AppData 같은 곳은 안 됨), off = 뺄 기본 폴더."""
    new = dict(current)
    for key in PERM_NAMES:
        if key in changes:
            if not isinstance(changes[key], bool):
                raise OfficeError("켜기/끄기 값이 이상해요.")
            new[key] = changes[key]
    if "extra" in changes:
        extra = []
        for raw in changes["extra"] if isinstance(changes["extra"], list) else []:
            path = Path(str(raw)).expanduser()
            if not path.is_dir():
                raise OfficeError(f"'{raw}' 폴더가 없어요.")
            path = path.resolve()
            if any(part.lower() in BLOCKED for part in path.parts) or len(path.parts) <= 1:
                raise OfficeError(f"'{raw}'은(는) 시스템·숨김 폴더라 허용할 수 없어요.")
            extra.append(str(path))
        new["extra"] = sorted(set(extra))
    if "off" in changes:
        new["off"] = sorted({k for k in changes["off"] if k in folders}) if isinstance(changes["off"], list) else []
    return new


def save_permissions(path: Path, settings: dict) -> None:
    tmp = Path(path).with_suffix(".tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def files_from(settings: dict, output: Path, folders: dict[str, Path] | None = None) -> Files:
    folders = default_folders() if folders is None else folders
    roots = [p for key, p in folders.items() if key not in settings["off"]] + [Path(p) for p in settings["extra"] if Path(p).exists()]
    roots.append(Path(output))  # 사무실 결과물도 열고 읽을 수 있게
    return Files(roots=roots, folders=folders, perms={k: settings[k] for k in PERM_NAMES})
