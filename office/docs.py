"""문서 판독: 한글·워드·파워포인트·엑셀·텍스트 파일에서 글자를 꺼낸다 (AI 없이)."""
import codecs
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

from office import OfficeError
from office.literature import html_to_text

MAX_FILE = 30_000_000   # 압축을 푼 XML 한 개, 글자 파일 한 개의 최대 크기
MAX_ROWS = 2000         # 엑셀은 앞쪽 줄만 (어차피 AI에는 앞부분만 들어간다)
PARA_TEXT = 67          # HWP 레코드: 문단 글자
SUPPORTED = "사진·PDF·한글(HWP·HWPX)·워드(DOCX)·파워포인트(PPTX)·엑셀(XLSX)·글자 파일(TXT·MD·CSV·HTML 등)"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _number(name: str) -> int:
    found = re.findall(r"\d+", Path(name).name)
    return int(found[-1]) if found else 0


def _xml(z: zipfile.ZipFile, name: str) -> ET.Element:
    with z.open(name) as f:
        data = f.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        raise OfficeError("문서가 너무 커. 나눠서 올려줘.")
    return ET.fromstring(data)


def _text_of(el: ET.Element) -> str:
    parts = []
    for node in el.iter():
        name = _local(node.tag)
        if name == "t":  # w:t · a:t · hp:t (instrText·delText 같은 숨은 글자는 뺀다)
            parts.append(node.text or "")
            parts.extend(child.tail or "" for child in node)
        elif name in ("tab", "br", "lineBreak"):
            parts.append(" ")
    return " ".join("".join(parts).split())


def _lines(el: ET.Element, out: list[str]) -> list[str]:
    for child in el:
        name = _local(child.tag)
        if name == "tr":  # 표 한 줄 = 칸 | 칸
            cells = [_text_of(c) for c in child if _local(c.tag) == "tc"]
            if any(cells):
                out.append(" | ".join(cells))
        elif name == "p" and not any(_local(d.tag) == "tbl" for d in child.iter()):
            if text := _text_of(child):
                out.append(text)
        else:
            _lines(child, out)
    return out


def _parts(z: zipfile.ZipFile, pattern: str) -> list[str]:
    return sorted((n for n in z.namelist() if re.fullmatch(pattern, n)), key=_number)


def _docx(z: zipfile.ZipFile) -> str:
    return "\n".join(_lines(_xml(z, "word/document.xml"), []))


def _hwpx(z: zipfile.ZipFile) -> str:
    return "\n".join(line for name in _parts(z, r"Contents/section\d+\.xml") for line in _lines(_xml(z, name), []))


def _pptx(z: zipfile.ZipFile) -> str:
    slides = [f"## 슬라이드 {i}\n" + "\n".join(_lines(_xml(z, name), []))
              for i, name in enumerate(_parts(z, r"ppt/slides/slide\d+\.xml"), 1)]
    return "\n\n".join(slides)


def _column(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + ord(ch.upper()) - 64
    return max(n - 1, 0)


def _xlsx(z: zipfile.ZipFile) -> str:
    strings = []
    if "xl/sharedStrings.xml" in z.namelist():
        strings = ["".join(t.text or "" for t in si.iter() if _local(t.tag) == "t")
                   for si in _xml(z, "xl/sharedStrings.xml") if _local(si.tag) == "si"]
    names = [s.get("name") for s in _xml(z, "xl/workbook.xml").iter() if _local(s.tag) == "sheet"]
    out = []
    # ponytail: 시트 파일 번호 순서 = 통합문서 순서로 본다 (시트를 옮긴 파일은 이름이 어긋날 수 있음)
    for i, name in enumerate(_parts(z, r"xl/worksheets/sheet\d+\.xml")):
        out.append(f"## 시트: {names[i] if i < len(names) else i + 1}")
        rows = 0
        for row in _xml(z, name).iter():
            if _local(row.tag) != "row" or rows >= MAX_ROWS:
                continue
            cells = {}
            for c in row:
                if _local(c.tag) != "c":
                    continue
                kind = c.get("t")
                value = next((v.text for v in c if _local(v.tag) == "v"), None) or ""
                if kind == "s" and value.isdigit():
                    value = strings[int(value)] if int(value) < len(strings) else ""
                elif kind == "inlineStr":
                    value = "".join(t.text or "" for t in c.iter() if _local(t.tag) == "t")
                cells[_column(c.get("r") or "")] = value.strip()
            if any(cells.values()):
                out.append("\t".join(cells.get(i, "") for i in range(max(cells) + 1)))
                rows += 1
    return "\n".join(out)


ZIP_DOCS = {".docx": _docx, ".hwpx": _hwpx, ".pptx": _pptx, ".xlsx": _xlsx}


def read_zip_doc(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            return ZIP_DOCS[path.suffix.lower()](z)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        raise OfficeError(f"{path.suffix.upper().lstrip('.')} 파일이 깨졌거나 내용이 없어. 다시 저장해서 올려줘.") from e


# ---- 옛 한글 파일 (HWP 5: OLE 안에 압축된 레코드) ----
def _hwp_chars(raw: bytes) -> str:
    keep, i = bytearray(), 0
    while i + 2 <= len(raw):
        code = int.from_bytes(raw[i:i + 2], "little")
        if code >= 32:
            keep += raw[i:i + 2]
            i += 2
        elif code in (0, 10, 13) or code >= 24:  # 글자 하나 크기 조종 문자
            if code == 10:
                keep += "\n".encode("utf-16-le")
            elif code in (30, 31):
                keep += " ".encode("utf-16-le")
            i += 2
        else:  # 표·그림·탭 같은 조종 문자는 8글자 크기
            if code == 9:
                keep += "\t".encode("utf-16-le")
            i += 16
    return keep.decode("utf-16-le", "replace").strip()


def hwp_paragraphs(data: bytes) -> list[str]:
    out, i = [], 0
    while i + 4 <= len(data):
        header = int.from_bytes(data[i:i + 4], "little")
        i += 4
        tag, size = header & 0x3FF, header >> 20
        if size == 0xFFF:
            size = int.from_bytes(data[i:i + 4], "little")
            i += 4
        if tag == PARA_TEXT:
            out.append(_hwp_chars(data[i:i + size]))
        i += size
    return out


def read_hwp(path: Path, open_ole=None) -> str:
    if open_ole is None:
        import olefile
        open_ole = olefile.OleFileIO
    broken = "한글 파일이 아니거나 깨졌어. 한글에서 다시 저장하거나 PDF로 올려줘."
    try:
        ole = open_ole(str(path))
    except OSError as e:
        raise OfficeError(broken) from e
    with ole:
        if not ole.exists("FileHeader"):
            raise OfficeError(broken)
        flags = int.from_bytes(ole.openstream("FileHeader").read()[36:40], "little")
        if flags & 2:
            raise OfficeError("암호가 걸린 한글 파일은 못 읽어. 암호를 풀고 다시 저장해줘.")
        if flags & 4:
            raise OfficeError("배포용 한글 파일은 못 읽어. 한글에서 PDF로 저장해서 올려줘.")
        sections = sorted((e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText"),
                          key=lambda e: _number(e[1]))
        paragraphs = []
        for entry in sections:
            data = ole.openstream(entry).read()
            try:
                data = zlib.decompress(data, -15) if flags & 1 else data
            except zlib.error as e:
                raise OfficeError(broken) from e
            paragraphs += hwp_paragraphs(data)
    return "\n".join(p for p in paragraphs if p)


# ---- 글자 파일 ----
def read_text(path: Path) -> str | None:
    """글자 파일이면 내용, 아니면(이진 파일) None."""
    if path.stat().st_size > MAX_FILE:
        raise OfficeError("파일이 너무 커. 나눠서 올려줘.")
    raw = path.read_bytes()
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        text = raw.decode("utf-16", "replace")
    elif b"\x00" in raw[:4096]:
        return None
    else:
        for encoding in ("utf-8-sig", "cp949"):  # 옛 메모장 파일은 cp949
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", "replace")
    if path.suffix.lower() in (".html", ".htm"):
        text = html_to_text(text)
    return text.replace("\r\n", "\n").strip()
