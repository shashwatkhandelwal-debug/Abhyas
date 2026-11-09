"""Unit tests for README and documentation limits (spec/13, Job 09)."""

from pathlib import Path


def test_readme_privacy_design_clarity() -> None:
    """Verifies README clearly states that teacher practice is confidential and never shown by name."""
    readme_path = Path("README.md")
    assert readme_path.exists()
    content = readme_path.read_text(encoding="utf-8")

    assert "Teacher practice is never shown by teacher name" in content or "never shown by teacher name" in content
    assert "school-level aggregates only" in content
    assert "n < 10 suppression" in content
    assert "Two-Tier Consent" in content or "separate opt-in" in content


def test_readme_evidence_page_link() -> None:
    """Verifies README links to docs/evidence/README.md and cites core benchmark categories."""
    readme_path = Path("README.md")
    content = readme_path.read_text(encoding="utf-8")

    assert "docs/evidence/README.md" in content
    assert "Cost per Teacher Loop" in content
    assert "15 Input/Output Guards" in content
    assert "8/8" in content


def test_readme_what_this_does_not_do_section() -> None:
    """Verifies README has a prominent 'What This Does NOT Do' section with clear boundaries."""
    readme_path = Path("README.md")
    content = readme_path.read_text(encoding="utf-8")

    assert "## What This Does NOT Do" in content
    assert "Does NOT replace human teachers" in content
    assert "Does NOT grade, rank, or discipline teachers" in content
    assert "Does NOT let LLMs decide simulated child answers" in content
    assert "Does NOT hallucinate ungrounded handbook advice" in content
    assert "Does NOT execute AI inference offline" in content
    assert "Does NOT claim verified field pilot results" in content


def test_readme_links_to_key_docs() -> None:
    """Verifies README links to JUDGE_DEMO_SCRIPT.md and OFFLINE_CAPABILITIES.md."""
    readme_path = Path("README.md")
    content = readme_path.read_text(encoding="utf-8")

    assert "docs/JUDGE_DEMO_SCRIPT.md" in content
    assert "docs/OFFLINE_CAPABILITIES.md" in content


def test_deck_outline_reflects_privacy_and_evidence() -> None:
    """Verifies DECK_OUTLINE.md reflects privacy design and evidence page."""
    deck_path = Path("docs/submission/DECK_OUTLINE.md")
    assert deck_path.exists()
    content = deck_path.read_text(encoding="utf-8")

    assert "school-level aggregates" in content
    assert "docs/evidence/README.md" in content
