from pathlib import Path

from PIL import Image


def _opaque_bbox(img: Image.Image) -> tuple[int, int, int, int]:
    return img.getchannel("A").point(lambda a: 255 if a > 128 else 0).getbbox()


def _hard_alpha(img: Image.Image) -> Image.Image:
    img.putalpha(img.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
    return img


def build_pixel_logo(src: Path, out: Path, width: int = 128, scale: int = 3) -> None:
    img = Image.open(src).convert("RGBA")
    img = img.crop(_opaque_bbox(img))
    height = max(1, round(img.height * width / img.width))
    small = _hard_alpha(img.resize((width, height), Image.LANCZOS))
    small.resize((width * scale, height * scale), Image.NEAREST).save(out)
