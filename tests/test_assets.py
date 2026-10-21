from PIL import Image
from office.assets import build_pixel_logo
from office.config import LOGO

def test_pixel_logo_is_crisp(tmp_path):
    out = tmp_path / "logo.png"
    build_pixel_logo(LOGO, out, width=64, scale=3)
    img = Image.open(out).convert("RGBA")
    assert img.width == 192 and img.height % 3 == 0
    assert set(img.getchannel("A").tobytes()) <= {0, 255}

from office.assets import build_icon

def test_icon_has_all_sizes(tmp_path):
    out = tmp_path / "icon.ico"
    build_icon(LOGO, out)
    assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= Image.open(out).info["sizes"]
