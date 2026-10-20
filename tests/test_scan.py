import io
import pytest
from PIL import Image
from office import OfficeError
from office.config import MAX_IMAGE_SIDE, MAX_PAGES, MAX_INPUT_CHARS
from office.scan import load_pages, scan

def _text_pdf(path):
    stream = b"BT /F1 12 Tf 50 800 Td (This handout has a real text layer so no OCR is needed here.) Tj ET"
    objs = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
            b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>",
            b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
            b"<</Length %d>>stream\n" % len(stream) + stream + b"\nendstream"]
    body = b"%PDF-1.4\n" + b"".join(b"%d 0 obj\n" % (i + 1) + o + b"\nendobj\n" for i, o in enumerate(objs))
    path.write_bytes(body + b"trailer<</Root 1 0 R>>\n%%EOF\n")   # xref 없음: pdfium이 복구해서 읽음

def test_exif_rotated_photo_is_upright(tmp_path):
    p = tmp_path / "photo.jpg"
    exif = Image.Exif(); exif[0x0112] = 6
    Image.new("RGB", (200, 100), "white").save(p, "JPEG", exif=exif)
    [page] = load_pages(p)
    assert Image.open(io.BytesIO(page)).size == (100, 200)

def test_big_photo_is_shrunk(tmp_path):
    p = tmp_path / "big.png"; Image.new("RGB", (4000, 3000)).save(p)
    [page] = load_pages(p)
    assert max(Image.open(io.BytesIO(page)).size) == MAX_IMAGE_SIDE

def test_heic_is_rejected_with_hint(tmp_path):
    p = tmp_path / "a.heic"; p.write_bytes(b"x")
    with pytest.raises(OfficeError, match="JPG"):
        load_pages(p)

def test_image_only_pdf_becomes_image(tmp_path):
    p = tmp_path / "scan.pdf"; Image.new("RGB", (595, 842), "white").save(p)
    [page] = load_pages(p)
    assert isinstance(page, bytes)

def test_text_pdf_uses_text_layer(tmp_path):
    p = tmp_path / "digital.pdf"; _text_pdf(p)
    [page] = load_pages(p)
    assert isinstance(page, str) and "real text layer" in page

def test_too_many_pages(tmp_path):
    p = tmp_path / "long.pdf"
    pages = [Image.new("RGB", (100, 100)) for _ in range(MAX_PAGES + 1)]
    pages[0].save(p, save_all=True, append_images=pages[1:])
    with pytest.raises(OfficeError, match=str(MAX_PAGES)):
        load_pages(p)

def test_scan_joins_pages_and_takes_title(tmp_path):
    a, b = tmp_path / "1.png", tmp_path / "2.png"
    Image.new("RGB", (50, 50)).save(a); Image.new("RGB", (50, 50)).save(b)
    replies = iter(["# 세포의 구조\n- 핵", "## 세포막\n- 선택적 투과"])
    m = scan([a, b], llm=lambda system, user, **kw: next(replies))
    assert m.title == "세포의 구조" and m.sources == ["1.png", "2.png"]
    assert m.markdown == "# 세포의 구조\n- 핵\n\n---\n\n## 세포막\n- 선택적 투과" and m.warnings == []

def test_long_material_warns(tmp_path):
    a = tmp_path / "1.png"; Image.new("RGB", (50, 50)).save(a)
    m = scan([a], llm=lambda system, user, **kw: "가" * (MAX_INPUT_CHARS + 1))
    assert "앞 8000자만" in m.warnings[0]
