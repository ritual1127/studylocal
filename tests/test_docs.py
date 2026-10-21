import io
import zipfile
import zlib
import pytest
from PIL import Image
from office import OfficeError
from office.docs import hwp_paragraphs, read_hwp
from office.scan import first_title, load_pages, scan

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
A = ('xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
     'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"')
HP = ('xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
      'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"')
S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'


def make_zip(path, files):
    with zipfile.ZipFile(path, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return path


def no_ai(*args, **kwargs):
    raise AssertionError("문서는 AI 없이 읽어야 해")


def read(path):
    [page] = load_pages(path)
    assert isinstance(page, str)
    return page


def test_docx_paragraphs_and_table_rows(tmp_path):
    body = ('<w:p><w:r><w:t>세포의 구조</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>핵은</w:t></w:r><w:r><w:t xml:space="preserve"> 유전 물질을 담는다.</w:t></w:r></w:p>'
            '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>소기관</w:t></w:r></w:p></w:tc>'
            '<w:tc><w:p><w:r><w:t>하는 일</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
            '<w:p><w:r><w:instrText>PAGE</w:instrText></w:r></w:p>')
    path = make_zip(tmp_path / "a.docx", {"word/document.xml": f"<w:document {W}><w:body>{body}</w:body></w:document>"})
    m = scan([path], llm=no_ai)
    assert m.markdown == "세포의 구조\n핵은 유전 물질을 담는다.\n소기관 | 하는 일" and m.title == "세포의 구조"


def test_pptx_slides_in_number_order(tmp_path):
    def slide(*texts):
        shapes = "".join(f"<p:sp><p:txBody><a:p><a:r><a:t>{t}</a:t></a:r></a:p></p:txBody></p:sp>" for t in texts)
        return f"<p:sld {A}><p:cSld><p:spTree>{shapes}</p:spTree></p:cSld></p:sld>"
    path = make_zip(tmp_path / "b.pptx", {"ppt/slides/slide1.xml": slide("광합성", "빛 에너지"),
                                          "ppt/slides/slide10.xml": slide("정리"),
                                          "ppt/slides/slide2.xml": slide("명반응")})
    assert read(path) == "## 슬라이드 1\n광합성\n빛 에너지\n\n## 슬라이드 2\n명반응\n\n## 슬라이드 3\n정리"
    assert scan([path], llm=no_ai).title == "광합성"


def test_hwpx_sections_and_tables(tmp_path):
    sec0 = (f"<hs:sec {HP}><hp:p><hp:run><hp:t>운수 좋은 날</hp:t></hp:run></hp:p>"
            "<hp:p><hp:run><hp:tbl><hp:tr>"
            "<hp:tc><hp:subList><hp:p><hp:run><hp:t>인물</hp:t></hp:run></hp:p></hp:subList></hp:tc>"
            "<hp:tc><hp:subList><hp:p><hp:run><hp:t>김첨지</hp:t></hp:run></hp:p></hp:subList></hp:tc>"
            "</hp:tr></hp:tbl></hp:run></hp:p></hs:sec>")
    sec1 = f"<hs:sec {HP}><hp:p><hp:run><hp:t>현진건</hp:t></hp:run></hp:p></hs:sec>"
    path = make_zip(tmp_path / "c.hwpx", {"Contents/section1.xml": sec1, "Contents/section0.xml": sec0})
    assert read(path) == "운수 좋은 날\n인물 | 김첨지\n현진건"


def test_xlsx_rows_keep_columns(tmp_path):
    path = make_zip(tmp_path / "d.xlsx", {
        "xl/workbook.xml": f'<workbook {S}><sheets><sheet name="성적" sheetId="1"/></sheets></workbook>',
        "xl/sharedStrings.xml": f"<sst {S}><si><t>이름</t></si><si><t>점수</t></si><si><r><t>철</t></r><r><t>수</t></r></si></sst>",
        "xl/worksheets/sheet1.xml": (f'<worksheet {S}><sheetData>'
                                     '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                                     '<row r="2"><c r="A2" t="s"><v>2</v></c><c r="C2"><v>90</v></c></row>'
                                     '<row r="3"><c r="B3" t="inlineStr"><is><t>메모</t></is></c></row>'
                                     '</sheetData></worksheet>')})
    assert read(path) == "## 시트: 성적\n이름\t점수\n철수\t\t90\n\t메모"


def test_text_files_any_encoding_and_html(tmp_path):
    (tmp_path / "a.txt").write_bytes("가나다 메모".encode("cp949"))
    (tmp_path / "b.md").write_text("# 제목\n본문", encoding="utf-8")
    (tmp_path / "c.py").write_text("print('안녕')", encoding="utf-8")
    (tmp_path / "d.html").write_text("<html><body><h1>뉴스</h1><script>steal()</script><p>본문</p></body></html>",
                                     encoding="utf-8")
    (tmp_path / "e.csv").write_bytes("﻿이름,점수\n철수,90".encode("utf-8"))
    assert read(tmp_path / "a.txt") == "가나다 메모"
    assert read(tmp_path / "b.md") == "# 제목\n본문"
    assert read(tmp_path / "c.py") == "print('안녕')"
    html = read(tmp_path / "d.html")
    assert "뉴스" in html and "본문" in html and "steal" not in html
    assert read(tmp_path / "e.csv") == "이름,점수\n철수,90"


@pytest.mark.parametrize("name, data, hint", [
    ("song.mp3", b"ID3\x00\x01", "소리·영상"),
    ("clip.mp4", b"\x00\x00\x00\x18ftyp", "소리·영상"),
    ("old.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "옛날 형식"),
    ("blob.bin", b"\x00\x01\x02\x03", "못 읽어"),
    ("empty.docx", None, "글자"),
])
def test_unreadable_files_explain_why(tmp_path, name, data, hint):
    path = tmp_path / name
    if data is None:
        make_zip(path, {"word/document.xml": f"<w:document {W}><w:body><w:p/></w:body></w:document>"})
    else:
        path.write_bytes(data)
    with pytest.raises(OfficeError, match=hint):
        load_pages(path)


def test_broken_zip_document_is_reported(tmp_path):
    (tmp_path / "x.pptx").write_bytes(b"PK not really")
    with pytest.raises(OfficeError, match="깨졌"):
        load_pages(tmp_path / "x.pptx")


def test_more_image_formats_go_to_ocr(tmp_path):
    for name in ("a.bmp", "b.gif", "c.tiff"):
        Image.new("RGB", (50, 40), "white").save(tmp_path / name)
        [page] = load_pages(tmp_path / name)
        assert isinstance(page, bytes) and Image.open(io.BytesIO(page)).size == (50, 40)


# ---- HWP (옛 한글 파일, OLE 안의 레코드) ----
def rec(tag, payload):
    if len(payload) >= 0xFFF:
        return (tag | 0xFFF << 20).to_bytes(4, "little") + len(payload).to_bytes(4, "little") + payload
    return (tag | len(payload) << 20).to_bytes(4, "little") + payload


def u16(text):
    return text.encode("utf-16-le")


def ctrl(code, wide):
    return code.to_bytes(2, "little") + (b"\x00" * 14 if wide else b"")


def test_hwp_records_to_paragraphs():
    para = u16("가나") + ctrl(9, True) + u16("다") + ctrl(11, True) + u16("표") + ctrl(13, False)
    big = u16("라" * 3000)  # 4095바이트를 넘으면 크기가 따로 붙는다
    data = rec(66, b"\x00" * 22) + rec(67, para) + rec(67, big) + rec(67, u16("마") + ctrl(10, False) + u16("바"))
    assert hwp_paragraphs(data) == ["가나\t다표", "라" * 3000, "마\n바"]


class FakeOle:
    def __init__(self, flags, *sections):
        header = b"HWP Document File".ljust(32, b"\x00") + b"\x00\x00\x05\x05" + flags.to_bytes(4, "little")
        self.streams = {"FileHeader": header.ljust(256, b"\x00")}
        self.streams.update({f"BodyText/Section{i}": s for i, s in enumerate(sections)})

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def exists(self, name):
        return name in self.streams

    def listdir(self):
        return [name.split("/") for name in self.streams]

    def openstream(self, name):
        return io.BytesIO(self.streams["/".join(name) if isinstance(name, list) else name])


def deflate(data):
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(data) + c.flush()


def test_read_hwp_compressed_sections_in_order(tmp_path):
    s0, s1 = rec(67, u16("1단원 세포")), rec(67, u16("2단원 유전"))
    ole = FakeOle(1, deflate(s0), deflate(s1))
    assert read_hwp(tmp_path / "a.hwp", open_ole=lambda p: ole) == "1단원 세포\n2단원 유전"


@pytest.mark.parametrize("flags, hint", [(2, "암호"), (4, "배포용")])
def test_read_hwp_locked_documents(tmp_path, flags, hint):
    with pytest.raises(OfficeError, match=hint):
        read_hwp(tmp_path / "a.hwp", open_ole=lambda p: FakeOle(flags))


def test_not_really_hwp(tmp_path):
    (tmp_path / "fake.hwp").write_bytes(b"hello")
    with pytest.raises(OfficeError, match="한글 파일"):
        load_pages(tmp_path / "fake.hwp")


def test_first_title_skips_tables_lists_and_long_lines():
    assert first_title("## 슬라이드 1\n| 구분 | 내용 |\n- 목록\n2학기 중간 대비") == "2학기 중간 대비"
    assert first_title("## 시트: 성적\n이름\t점수\n\t메모") == ""
    assert first_title("가" * 41) == "" and first_title("본문\n# 진짜 제목") == "진짜 제목"
