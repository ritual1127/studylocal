"""화면 E2E: 설치된 Edge로 가짜 사무실(AI 없음)을 직접 눌러 본다. RITUAL_E2E=1 uv run pytest tests/test_ui.py"""
import os
import re
import tempfile
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("RITUAL_E2E") != "1", reason="화면 E2E는 RITUAL_E2E=1일 때만 (Edge 필요)")

PORT = 8799
URL = f"http://127.0.0.1:{PORT}/"


@pytest.fixture(scope="module")
def office():
    from ui_demo import make_demo_office, serve
    office = make_demo_office(Path(tempfile.mkdtemp(prefix="ritual-e2e-")))
    serve(office, PORT)
    return office


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="msedge")
        yield b
        b.close()


@pytest.fixture
def page(office, browser):
    ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, accept_downloads=True)
    p = ctx.new_page()
    p.set_default_timeout(10000)
    errors = []
    p.on("pageerror", lambda e: errors.append(str(e)))
    # 일부러 틀린 요청(빈 반려 등)의 400은 브라우저가 콘솔에 찍는다 → 스크립트 에러만 본다
    p.on("console", lambda m: errors.append(m.text) if m.type == "error" and "Failed to load resource" not in m.text else None)
    p.goto(URL)
    p.click("#welcomeGo")
    yield p
    assert errors == []  # 어떤 화면에서도 스크립트 에러가 없어야 한다
    ctx.close()


def pane(page, i):
    return page.locator(".pane").nth(i)


def tab(page, i, name):
    pane(page, i).get_by_role("tab", name=re.compile(f"^{name}")).click()


def card(page, text):
    return pane(page, 1).locator(".card", has_text=text).first


def command(page, text, files=()):
    from playwright.sync_api import expect
    if files:
        page.set_input_files("#pick", list(files))
    page.fill("#text", text)
    page.keyboard.press("Enter")
    expect(page.locator(".toast", has_text="실장님께 맡겼어요")).to_be_visible()


def test_welcome_shows_once_and_first_layout_is_office_and_vault(page):
    from playwright.sync_api import expect
    expect(page.locator("#welcome")).to_be_hidden()
    expect(pane(page, 0).locator(".tab.on")).to_have_text("사무실")
    expect(pane(page, 1).locator(".tab.on")).to_have_text("보관함")
    expect(page.locator(".desk")).to_have_count(18)  # 직원 16 + 대표실 문 + 휴게실
    page.reload()
    expect(page.locator("#welcome")).to_be_hidden()  # 두 번째부터는 안내 안 띄움


def test_question_is_answered_and_auto_approved(page):
    from playwright.sync_api import expect
    before = pane(page, 1).locator(".card", has_text="광합성 질문").count()
    command(page, "광합성이 뭐야?")
    expect(pane(page, 1).locator(".card", has_text="광합성 질문")).to_have_count(before + 1)
    c = card(page, "광합성 질문")
    expect(c.locator(".badge")).to_have_text("완료")
    expect(c.locator(".stamp")).to_have_text("자동승인")
    expect(c.locator(".answer-text b")).to_have_text("빛에너지")  # **굵게**가 살아 있다


def test_upload_then_ceo_rejects_then_approves(page, tmp_path):
    from playwright.sync_api import expect
    photo = tmp_path / "수업 프린트.jpg"
    photo.write_bytes(b"x")
    command(page, "이 프린트 정리해줘", [photo])
    tab(page, 1, "대표실")
    review = pane(page, 1).locator(".review-card", has_text="수업 프린트").first
    expect(review).to_be_visible()
    review.get_by_role("button", name="반려").click()
    expect(page.locator(".toast.err", has_text="고칠지")).to_be_visible()
    review.locator("textarea").fill("표를 더 넣어줘")
    review.get_by_role("button", name="반려").click()
    reworked = pane(page, 1).locator(".review-card", has_text="수업 프린트").first
    expect(reworked).to_contain_text("수정본 1")
    expect(reworked).to_contain_text("지난 반려 의견: 표를 더 넣어줘")
    reworked.locator("textarea").fill("좋아")
    reworked.get_by_role("button", name="승인").click()
    tab(page, 1, "보관함")
    expect(card(page, "수업 프린트").locator(".stamp")).to_have_text("승인")


def test_drag_and_drop_attaches_file(page):
    from playwright.sync_api import expect
    dt = page.evaluate_handle("""() => {
        const dt = new DataTransfer();
        dt.items.add(new File(["x"], "끌어온 자료.pdf", { type: "application/pdf" }));
        return dt;
    }""")
    page.dispatch_event("body", "dragenter", {"dataTransfer": dt})
    expect(page.locator("#drop")).to_be_visible()
    page.dispatch_event("body", "drop", {"dataTransfer": dt})
    expect(page.locator("#drop")).to_be_hidden()
    expect(page.locator("#chips .chip")).to_have_text(re.compile("끌어온 자료.pdf"))


def test_split_view_tabs_and_shortcuts(page):
    from playwright.sync_api import expect
    tab(page, 0, "보관함")  # 오른쪽에 있던 탭을 왼쪽에서 고르면 서로 바뀐다
    expect(pane(page, 0).locator(".tab.on")).to_have_text("보관함")
    expect(pane(page, 1).locator(".tab.on")).to_have_text("사무실")
    page.keyboard.press("Alt+S")
    expect(pane(page, 1)).to_be_hidden()
    page.keyboard.press("Alt+3")
    expect(pane(page, 0).locator(".tab.on")).to_have_text("오늘")
    page.keyboard.press("Alt+S")
    expect(pane(page, 1)).to_be_visible()
    page.reload()
    expect(pane(page, 0).locator(".tab.on")).to_have_text("오늘")  # 배치는 기억한다


def test_today_todo_add_check_and_move_overdue(page):
    from playwright.sync_api import expect
    tab(page, 0, "오늘")
    form = pane(page, 0).locator(".row-form")
    form.locator("input").first.fill("E2E 단어 외우기")
    form.locator("input").first.press("Enter")
    item = pane(page, 0).locator(".todo", has_text="E2E 단어 외우기")
    expect(item).to_be_visible()
    item.locator("input[type=checkbox]").check()
    expect(item).to_have_class(re.compile("done"))
    late = pane(page, 0).locator(".warnbox .todo", has_text="과학 실험 보고서")
    late.get_by_role("button", name="오늘로").click()
    expect(pane(page, 0).locator(".warnbox")).to_be_hidden()


def test_schedule_add_and_double_click_delete(page):
    from playwright.sync_api import expect
    tab(page, 0, "일정")
    form = pane(page, 0).locator("form.row-form")
    form.locator("input").first.fill("E2E 영어 학원")
    form.locator("input[type=time]").fill("16:00")
    form.get_by_role("button", name="일정 넣기").click()
    row = pane(page, 0).locator(".agenda .event", has_text="E2E 영어 학원")
    expect(row).to_be_visible()
    row.get_by_role("button", name=re.compile("지우기")).click()
    expect(row.locator(".btn.armed")).to_have_text("지울까?")
    row.locator(".btn.armed").click()
    expect(pane(page, 0).locator(".agenda .event", has_text="E2E 영어 학원")).to_have_count(0)


def test_focus_mode_runs_and_stops(page):
    from playwright.sync_api import expect
    page.keyboard.press("Alt+G")
    expect(page.locator("#focus")).to_be_visible()
    page.click("[data-focus='25']")
    expect(page.locator("#focusChip")).to_have_text(re.compile(r"집중 2[45]:\d\d"))
    page.click("#focusStop")
    expect(page.locator(".toast", has_text="공부모드 껐어")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#focus")).to_be_hidden()
    expect(page.locator("#focusChip")).to_be_hidden()


def test_settings_ai_mode_test_alert_and_backup(page, office):
    from playwright.sync_api import expect
    tab(page, 1, "설정")
    pane(page, 1).get_by_text("꼼꼼", exact=True).click()
    expect(page.locator("#model")).to_have_text(re.compile("^꼼꼼"))
    pane(page, 1).get_by_text("빠름", exact=True).click()
    expect(page.locator("#model")).to_have_text(re.compile("^빠름"))
    pane(page, 1).get_by_role("button", name="테스트 알림").click()
    expect(page.locator(".toast.ok", has_text="테스트 알림 보냈어")).to_be_visible()
    assert "테스트 알림" in office.notifier.sent
    with page.expect_download() as dl:
        pane(page, 1).get_by_role("link", name="백업 받기").click()
    assert "planner.json" in zipfile.ZipFile(dl.value.path()).namelist()


def test_reuse_material_then_delete_job(page):
    from playwright.sync_api import expect
    source = card(page, "운수 좋은 날")
    source.get_by_role("button", name="이 자료로 더 하기").click()
    expect(page.locator("#chips .chip.ref")).to_contain_text("운수 좋은 날")
    command(page, "이걸로 문제 더")
    tab(page, 1, "대표실")
    review = pane(page, 1).locator(".review-card", has_text="운수 좋은 날").first
    review.get_by_role("button", name="승인").click()
    tab(page, 1, "보관함")
    newest = pane(page, 1).locator(".card").first
    expect(newest).to_contain_text("운수 좋은 날")
    expect(newest.get_by_role("link", name="문제 풀기")).to_be_visible()
    newest.get_by_role("button", name="지우기").click()
    newest.get_by_role("button", name="정말 지울까요? 한 번 더").click()
    expect(page.locator(".toast", has_text="지웠어")).to_be_visible()


def test_phone_page_with_token(page, browser, office):
    from playwright.sync_api import expect
    tab(page, 1, "설정")
    pane(page, 1).get_by_text("같은 와이파이", exact=True).click()
    link = pane(page, 1).locator(".remote-link code")
    expect(link).to_contain_text("/m?k=")
    expect(pane(page, 1).locator("img.qr")).to_be_visible()
    phone = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True).new_page()
    phone.goto("http://127.0.0.1:8798/m")
    expect(phone.locator("h1")).to_have_text("잠겨 있어")
    phone.goto(link.inner_text())
    expect(phone.locator("#status")).to_have_text(re.compile("^PC (연결됨|AI 꺼짐)"))
    phone.fill("#text", "광합성 조사해서 암기카드랑 마인드맵")
    phone.click("#send")
    expect(phone.locator(".toast.ok")).to_be_visible()
    phone.get_by_role("tab", name=re.compile("^결재")).click()
    first = phone.locator("#review .card").first
    first.locator("textarea").fill("폰 결재")
    first.get_by_role("button", name="승인").click()
    expect(phone.locator(".toast.ok", has_text="승인했어")).to_be_visible()
    assert any(j.approvals and j.approvals[-1]["comment"] == "폰 결재" for j in office.jobs.values())
    pane(page, 1).get_by_text("끔", exact=True).click()
    expect(pane(page, 1).locator(".remote-link")).to_have_count(0)
    phone.context.close()


def test_team_popup_shows_four_and_assigns_work(page):
    from playwright.sync_api import expect
    pane(page, 0).get_by_role("button", name="번역가 팀 보기 (4인 1조)").click()
    popup = page.locator("#team")
    expect(popup).to_be_visible()
    expect(popup.locator(".member")).to_have_count(4)
    expect(popup).to_contain_text("에밀리")
    popup.get_by_role("button", name="번역가 팀에 시키기").click()
    expect(popup).to_be_hidden()
    expect(page.locator("#text")).to_have_value(re.compile("^@번역가 "))


def test_history_mode_lists_all_and_card_buttons(page):
    from playwright.sync_api import expect
    vault = pane(page, 1)
    vault.get_by_role("button", name="전체 기록").click()
    expect(vault.locator(".day-group").first).to_be_visible()
    expect(vault.locator(".muted", has_text="전체")).to_contain_text("건")
    first = vault.locator(".card").first
    first.get_by_role("button", name="☆ 즐겨찾기").click()
    expect(page.locator(".toast.err")).to_have_count(0)
    vault.locator(".filters").get_by_role("button", name=re.compile("^★")).click()
    expect(vault.locator(".card .star").first).to_be_visible()
    vault.get_by_role("button", name="최근").click()
    first = vault.locator(".card").first
    first.get_by_role("button", name="제목 바꾸기").click()
    first.locator(".rename input").fill("E2E 새 제목")
    first.locator(".rename input").press("Enter")
    expect(vault.locator(".card h3", has_text="E2E 새 제목")).to_be_visible()


def test_quick_chips_and_command_recall(page):
    from playwright.sync_api import expect
    page.locator("#quick").get_by_role("button", name="폰으로 보내기").click()
    expect(page.locator("#text")).to_have_value("내 폰으로 ○○라고 보내")
    page.keyboard.type("굿나잇")  # ○○ 자리가 골라져 있어서 바로 바뀐다
    expect(page.locator("#text")).to_have_value("내 폰으로 굿나잇라고 보내")
    page.fill("#text", "안녕")
    page.keyboard.press("Enter")
    expect(page.locator(".toast", has_text="실장님께 맡겼어요")).to_be_visible()
    page.locator("#text").press("ArrowUp")
    expect(page.locator("#text")).to_have_value("안녕")


def test_memory_section_add_and_forget(page):
    from playwright.sync_api import expect
    tab(page, 1, "설정")
    box = pane(page, 1).locator("section", has_text="실장님 기억")
    box.locator("input").fill("E2E 기억: 영어는 아침에")
    box.get_by_role("button", name="기억하기").click()
    item = box.locator("li", has_text="E2E 기억: 영어는 아침에")
    expect(item).to_be_visible()
    item.get_by_role("button", name=re.compile("잊기")).click()
    expect(box.locator("li", has_text="E2E 기억")).to_have_count(0)
