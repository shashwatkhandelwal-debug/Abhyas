"""fix5 item 5: the coach console title does not break mid-word; table headers stay readable in both themes."""

from pathlib import Path

TEMPLATES = Path(__file__).parents[2] / "app/web/templates"


def test_review_title_never_breaks_inside_a_word() -> None:
    html = (TEMPLATES / "review.html").read_text(encoding="utf-8")
    assert ".review-title-group h1 span { overflow-wrap: normal;" in html
    assert "white-space: nowrap" in html.split(".review-title-group h1 span")[1].split("}")[0]


def test_table_headers_do_not_use_a_fixed_pale_background() -> None:
    # a pale fixed fill with the theme ink colour is near-invisible on the dark theme
    for name in ("review.html", "trainer.html", "review_detail.html"):
        assert "#F4EFEA" not in (TEMPLATES / name).read_text(encoding="utf-8").upper()


def test_demo_banner_has_no_second_logout_link() -> None:
    html = (TEMPLATES / "teacher.html").read_text(encoding="utf-8")
    banner = next(ln for ln in html.splitlines() if 'id="demo-banner"' in ln)
    assert "/logout" not in banner
    assert 'class="header-logout"' in html  # the top bar keeps its one visible link
