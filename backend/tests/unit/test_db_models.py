"""Tests for database migrations, model schema completeness, and round-trips (§14 T03)."""

from alembic.config import Config
from alembic.script import ScriptDirectory

from backend.app.db.base import Base


def test_all_models_present_in_metadata() -> None:
    """Verify that every table defined in spec/03 is registered in Base.metadata."""
    expected_tables = {
        "batch",
        "cluster",
        "app_user",
        "teacher",
        "teacher_contact",
        "invite_code",
        "arp_assignment",
        "consent_log",
        "content_release",
        "move",
        "persona",
        "bug_rule",
        "session_state",
        "move_path",
        "scene",
        "turn",
        "message",
        "rehearsal_score",
        "explain_score",
        "adoption_evidence",
        "realism_rating",
        "question",
        "doc_chunk",
        "review_item",
        "calibration_label",
        "arp_observation",
        "scheduled_job",
        "template_send",
        "llm_call",
        "speech_spend",
        "tts_audio",
        "agg_module_batch",
    }
    actual_tables = set(Base.metadata.tables.keys())
    missing = expected_tables - actual_tables
    assert not missing, f"Missing tables in metadata: {missing}"


def test_alembic_migration_revisions_chain() -> None:
    """Verify that Alembic migrations form a valid contiguous chain from base to head."""
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    heads = script.get_heads()
    assert len(heads) == 1
    head_rev = heads[0]
    assert head_rev == "b3d5f7a9c1e4"

    rev_modules = script.get_revision(head_rev)
    assert rev_modules is not None
    assert rev_modules.down_revision == "a9c3e5f7b1d2"

    rev_progress = script.get_revision("f8a2b4c6d1e7")
    assert rev_progress is not None
    assert rev_progress.down_revision == "d5f7a9b1c3e6"

    rev_rating = script.get_revision("d5f7a9b1c3e6")
    assert rev_rating is not None
    assert rev_rating.down_revision == "b4d6f8a0c2e5"

    rev_lang = script.get_revision("b4d6f8a0c2e5")
    assert rev_lang is not None
    assert rev_lang.down_revision == "a3c5e7f9b1d4"

    rev_cit = script.get_revision("a3c5e7f9b1d4")
    assert rev_cit is not None
    assert rev_cit.down_revision == "e7f1a3b5c9d2"

    rev = script.get_revision("e7f1a3b5c9d2")
    assert rev is not None
    assert rev.down_revision == "c4e1f7a2b9d3"

    rev_drop = script.get_revision("c4e1f7a2b9d3")
    assert rev_drop is not None
    assert rev_drop.down_revision == "b2d91f8c7e3a"

    mid_rev = script.get_revision("b2d91f8c7e3a")
    assert mid_rev is not None
    assert mid_rev.down_revision == "6a7a8609f2ce"

    base_rev = script.get_revision("6a7a8609f2ce")
    assert base_rev is not None
    assert base_rev.down_revision is None
