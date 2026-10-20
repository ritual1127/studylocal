import io
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps

from office import Material, OfficeError, quiet
from office.config import MAX_IMAGE_SIDE, MAX_INPUT_CHARS, MAX_PAGES
from office.llm import chat

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
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
    raise OfficeError("JPG·PNG·WEBP·PDF만 읽을 수 있어. 아이폰 사진은 설정 > 카메라 > 포맷 > '높은 호환성'으로 찍어줘.")


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
    title = next((line[2:].strip() for line in markdown.splitlines() if line.startswith("# ")), Path(files[0]).stem)
    warnings = []
    if len(markdown) > MAX_INPUT_CHARS:
        warnings.append(f"자료가 길어서({len(markdown)}자) 앞 {MAX_INPUT_CHARS}자만 정리에 써.")
    return Material(title=title, markdown=markdown, sources=[Path(f).name for f in files], warnings=warnings)
