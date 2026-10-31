"""fix4 browser checks: one-submit login for every role, a Log out button on every role page, and
the login/logout cycle that used to leave messages on the sending clock (empty IndexedDB)."""

from typing import Any

import pytest

from backend.tests.e2e.conftest import DEMO_PASSWORD, MOBILE

ROLE_HOME = {
    "teacher.demo1": "/teacher",
    "teacher.demo2": "/teacher",
    "teacher.demo3": "/teacher",
    "arp.demo": "/arp",
    "trainer.demo": "/trainer",
    "coach.demo": "/review",
}


def _login(page: Any, base: str, user: str) -> None:
    page.goto(f"{base}/login")
    page.fill("#username", user)
    page.fill("#password", DEMO_PASSWORD)
    page.click("button[type=submit]")  # exactly one submit
    page.wait_for_load_state("networkidle")


def _to_chat(page: Any, base: str) -> None:
    if page.url.endswith("/teacher/start"):
        page.click("#start-go")
    page.wait_for_selector("#chat-input")
    page.wait_for_timeout(500)


def _new_page(browser: Any) -> tuple[Any, Any]:
    context = browser.new_context(viewport=MOBILE, is_mobile=True, has_touch=True)
    return context, context.new_page()


@pytest.mark.parametrize("user", list(ROLE_HOME))
def test_one_submit_logs_in_and_lands_on_the_role_page_with_a_logout_button(
    browser: Any, server: str, user: str
) -> None:
    context, page = _new_page(browser)
    try:
        _login(page, server, user)
        path = ROLE_HOME[user]
        assert page.url.split(server)[1].startswith(path), page.url
        assert "/login" not in page.url
        if path == "/teacher":
            _to_chat(page, server)
        logout = page.locator('a[href="/logout"]')
        assert logout.count() >= 1, f"{user}: no Log out link on {page.url}"
        assert any(logout.nth(i).is_visible() for i in range(logout.count())), (
            f"{user}: Log out is not visible on {page.url}"
        )
    finally:
        context.close()


def _send_and_expect_delivered(page: Any, text: str) -> None:
    page.fill("#chat-input", text)
    page.click("#btn-send")
    page.get_by_text(text).first.wait_for(timeout=5000)
    # the clock must turn into a check (or the send visibly fails); it must never just stay
    page.wait_for_function(
        "() => !document.querySelector('.status-icon.sending')", timeout=15000
    )
    assert page.locator(".status-icon.failed").count() == 0


def _stores(page: Any) -> list[str]:
    return page.evaluate(
        """() => new Promise((resolve) => {
          const r = indexedDB.open('abhyas_chat_db');
          r.onsuccess = () => { const n = [...r.result.objectStoreNames].sort(); r.result.close(); resolve(n); };
          r.onerror = () => resolve(['error']);
        })"""
    )


def test_login_logout_cycle_three_times_then_second_tab(browser: Any, server: str) -> None:
    context, page = _new_page(browser)
    try:
        for round_no in range(3):
            for user in ("teacher.demo1", "teacher.demo2", "teacher.demo3"):
                _login(page, server, user)
                _to_chat(page, server)
                assert _stores(page) == ["messages_cache", "outbox"], (round_no, user)
                _send_and_expect_delivered(page, f"नमस्ते {round_no}")
                page.click('a[href="/logout"]', force=True) if page.locator(
                    'a[href="/logout"]:visible'
                ).count() else page.goto(f"{server}/logout")
                page.wait_for_url("**/login", timeout=15000)
        # a second tab of the same browser, logged in as another demo teacher
        _login(page, server, "teacher.demo1")
        _to_chat(page, server)
        tab2 = context.new_page()
        tab2.goto(f"{server}/teacher")
        tab2.wait_for_selector("#chat-input")
        tab2.wait_for_timeout(500)
        _send_and_expect_delivered(tab2, "दूसरा टैब")
        _send_and_expect_delivered(page, "पहला टैब")
        tab2.goto(f"{server}/logout")
        tab2.wait_for_url("**/login", timeout=15000)
        _login(tab2, server, "teacher.demo2")
        _to_chat(tab2, server)
        _send_and_expect_delivered(tab2, "फिर से")
    finally:
        context.close()


def test_delete_my_data_on_a_demo_teacher_then_login_still_works(browser: Any, server: str) -> None:
    context, page = _new_page(browser)
    try:
        _login(page, server, "teacher.demo2")
        _to_chat(page, server)
        _send_and_expect_delivered(page, "डेटा हटाने से पहले")
        page.goto(f"{server}/teacher/delete")
        page.click("#btn-confirm-delete")
        page.wait_for_load_state("networkidle")
        page.goto(f"{server}/login")
        _login(page, server, "teacher.demo2")
        _to_chat(page, server)
        assert _stores(page) == ["messages_cache", "outbox"]
        _send_and_expect_delivered(page, "हटाने के बाद")
    finally:
        context.close()


@pytest.mark.parametrize("before", ["teacher.demo1", "arp.demo", "trainer.demo", None])
def test_coach_logs_in_with_one_submit_after_another_role_with_the_service_worker_active(
    browser: Any, server: str, before: str | None
) -> None:
    context, page = _new_page(browser)
    try:
        if before:
            _login(page, server, before)
            if page.url.endswith("/teacher/start"):
                page.click("#start-go")
            page.evaluate("() => navigator.serviceWorker.ready.then(() => true)")
            page.goto(f"{server}/logout")
            page.wait_for_url("**/login")
        _login(page, server, "coach.demo")
        assert page.url.rstrip("/").endswith("/review"), page.url
        assert page.locator('a[href="/logout"]').first.is_visible()
    finally:
        context.close()
