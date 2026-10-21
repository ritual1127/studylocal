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


ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]


def build_icon(src: Path, out: Path) -> None:
    img = Image.open(src).convert("RGBA")
    letter = img.crop((0, 0, 305, img.height))  # 로고 왼쪽 = 글자 "r"
    letter = letter.crop(_opaque_bbox(letter))
    side = max(letter.size)
    square = Image.new("RGBA", (side, side))
    square.paste(letter, ((side - letter.width) // 2, (side - letter.height) // 2))
    r = _hard_alpha(square.resize((24, 24), Image.LANCZOS))
    tile = Image.new("RGBA", (32, 32), "#9337FD")
    tile.paste(Image.new("RGBA", (30, 30), "#14111f"), (1, 1))
    tile.paste(r, (4, 4), r)
    frames = [tile.resize((s, s), Image.NEAREST) for s in ICON_SIZES]
    # ICO는 첫 이미지보다 큰 크기를 버리므로 가장 큰 것을 바탕으로 저장
    frames[-1].save(out, format="ICO", sizes=[(s, s) for s in ICON_SIZES], append_images=frames[:-1])


if __name__ == "__main__":
    from office.config import LOGO, WEB

    build_pixel_logo(LOGO, WEB / "logo-pixel.png")
    build_icon(LOGO, WEB / "icon.ico")
    print("web/logo-pixel.png, web/icon.ico 만들었어")
