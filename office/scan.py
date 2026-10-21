import io
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps

from office import Material, OfficeError, quiet
from office.config import MAX_IMAGE_SIDE, MAX_INPUT_CHARS, MAX_PAGES
from office.docs import SUPPORTED, ZIP_DOCS, read_hwp, read_text, read_zip_doc
from office.llm import chat

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
MEDIA_EXT = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma", ".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm"}
OLD_OFFICE = {".doc", ".ppt", ".xls"}
TEXT_LAYER_MIN = 50

OCR_SYSTEM = """너는 '공부 사무실'의 스캐너 직원이다. 사진 속 학교 프린트의 글자를 빠짐없이 그대로 마크다운으로 옮긴다.
제목은 #, 소제목은 ##, 목록은 -, 표는 마크다운 표로 쓴다.
사진에 없는 내용은 절대 쓰지 않는다. 설명이나 인사말 없이 옮긴 내용만 출력한다."""


def _normalize(img: Image.Image) -> bytes:
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def load_pages(path: Path) -> list[bytes | str]:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXT:
        with Image.open(path) as img:
            return [_normalize(img)]
    if suffix == ".pdf":
        pdf = pdfium.PdfDocument(path)
        try:
            if len(pdf) > MAX_PAGES:
                raise OfficeError(f"PDF가 {len(pdf)}쪽이야. {MAX_PAGES}쪽까지만 돼. 나눠서 올려줘.")
            pages = []
            for page in pdf:
                text = page.get_textpage().get_text_range().strip()
                pages.append(text if len(text) >= TEXT_LAYER_MIN else _normalize(page.render(scale=2).to_pil()))
            return pages
        finally:
            pdf.close()
    if suffix in (".heic", ".heif"):
        raise OfficeError("아이폰 HEIC 사진은 못 읽어. 설정 > 카메라 > 포맷 > '높은 호환성'으로 찍거나 JPG로 바꿔서 올려줘.")
    if suffix in MEDIA_EXT:
        raise OfficeError("소리·영상 파일은 아직 못 읽어. 내용을 글·사진·PDF로 올려줘.")
    if suffix in OLD_OFFICE:
        raise OfficeError("옛날 형식(.doc·.ppt·.xls)은 못 읽어. 새 형식(.docx·.pptx·.xlsx)이나 PDF로 저장해서 올려줘.")
    if suffix in ZIP_DOCS:
        text = read_zip_doc(path)
    elif suffix == ".hwp":
        text = read_hwp(path)
    else:
        text = read_text(path)
        if text is None:
            raise OfficeError(f"이 파일은 못 읽어. {SUPPORTED}만 돼.")
    if not text.strip():
        raise OfficeError("파일에서 글자를 못 찾았어. 사진이나 PDF로 올려줘.")
    return [text]


def first_title(markdown: str) -> str:
    """# 제목, 없으면 앞쪽의 짧은 첫 줄 (표·목록 줄은 빼고). 못 찾으면 빈 문자열 → 실장이 지은 제목을 쓴다."""
    lines = [line for line in markdown.splitlines() if line.strip()]
    heading = next((line[2:].strip() for line in lines if line.startswith("# ")), "")
    if heading:
        return heading
    for line in lines[:5]:
        text = line.strip()
        if "	" not in line and "|" not in text and not text.startswith(("#", "-", "*", ">")) and len(text) <= 40:
            return text
    return ""


def scan(files: list[Path], llm=chat, say=quiet) -> Material:
    pages = [page for f in files for page in load_pages(Path(f))]
    if len(pages) > MAX_PAGES:
        raise OfficeError(f"사진·쪽이 모두 {len(pages)}장이야. {MAX_PAGES}장까지만 돼.")
    parts = []
    for i, page in enumerate(pages, 1):
        say(f"{i}/{len(pages)}쪽 읽는 중")
        if isinstance(page, str):
            parts.append(page)
        else:
            parts.append(llm(OCR_SYSTEM, "이 프린트를 마크다운으로 옮겨줘.", images=[page], temperature=0).strip())
    markdown = "\n\n---\n\n".join(parts)
    title = first_title(markdown)
    warnings = []
    if len(markdown) > MAX_INPUT_CHARS:
        warnings.append(f"자료가 길어서({len(markdown)}자) 앞 {MAX_INPUT_CHARS}자만 정리에 써.")
    return Material(title=title, markdown=markdown, sources=[Path(f).name for f in files], warnings=warnings)
