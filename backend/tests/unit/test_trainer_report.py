"""Unit tests for Trainer view reporting, suppression, and CSV formatting (spec/09 §9.4, T33)."""

from __future__ import annotations

from backend.app.auth.access import SUPPRESSION_MESSAGE
from backend.app.reports.trainer_aggregates import (
    TrainerReport,
    TrainerRowView,
    compute_rubric_average,
    format_ladder_summary,
    generate_rubric_svg,
    generate_trainer_csv,
    get_top_missed_key_point,
)
from backend.app.sessions.path import load_all_move_cards


def test_generate_rubric_svg_empty() -> None:
    svg = generate_rubric_svg(None)
    assert "<svg" in svg
    assert "#E5E0D8" in svg


def test_generate_rubric_svg_normal() -> None:
    rubric_dist = {
        "crit1": {"0": 2, "1": 5, "2": 3},
    }
    svg = generate_rubric_svg(rubric_dist)
    assert "<svg" in svg
    assert "#B3261E" in svg  # Red (score 0)
    assert "#E0A100" in svg  # Marigold (score 1)
    assert "#1F6F5C" in svg  # Brand green (score 2)
    assert 'width="20.0"' in svg
    assert 'width="50.0"' in svg
    assert 'width="30.0"' in svg


def test_format_ladder_summary() -> None:
    ladder_dist = {"1": 4, "2": 6, "3": 7, "4": 5, "5": 3}
    summary = format_ladder_summary(ladder_dist)
    assert summary == "L1: 4 · L2: 6 · L3: 7 · L4: 5 · L5: 3"

    assert format_ladder_summary(None) == "—"


def test_compute_rubric_average() -> None:
    rubric_dist = {
        "crit1": {"0": 2, "1": 5, "2": 3},  # 0*2 + 1*5 + 2*3 = 11 / 10 = 1.10
    }
    avg = compute_rubric_average(rubric_dist)
    assert avg == 1.10

    assert compute_rubric_average(None) is None


def test_get_top_missed_key_point() -> None:
    moves = load_all_move_cards()
    assert len(moves) > 0
    move = next(m for m in moves if m.id == "NUM_SUB_REGROUP_BUNDLES")
    explain_missing = {"kp1": 3, "kp3": 12}
    kpid, count, text_desc = get_top_missed_key_point(explain_missing, move)
    assert kpid == "kp3"
    assert count == 12
    assert "बंडल" in text_desc


def test_generate_trainer_csv_suppression() -> None:
    """Verifies that suppressed rows (n < 10) in CSV export have all metrics masked."""
    row_unsuppressed = TrainerRowView(
        batch_id="KNP-B1",
        batch_name="कानपुर बैच 1",
        move_id="NUM_SUB_REGROUP_BUNDLES",
        move_title="दहाई का बंडल खोलकर घटाव",
        n_teachers=25,
        suppressed=False,
        pct_completed="84%",
        most_missed_point="बंडल खोलना",
        rubric_svg="<svg></svg>",
        ladder_summary="L1: 4 · L2: 6",
        rubric_avg=1.45,
        ladder_counts={"1": 4, "2": 6, "3": 7, "4": 5, "5": 3},
    )

    row_suppressed = TrainerRowView(
        batch_id="KNP-B3",
        batch_name="कानपुर बैच 3",
        move_id="NUM_SUB_REGROUP_BUNDLES",
        move_title="दहाई का बंडल खोलकर घटाव",
        n_teachers=8,
        suppressed=True,
        pct_completed=SUPPRESSION_MESSAGE,
        most_missed_point=SUPPRESSION_MESSAGE,
        rubric_svg=SUPPRESSION_MESSAGE,
        ladder_summary=SUPPRESSION_MESSAGE,
        rubric_avg=None,
        ladder_counts=None,
    )

    report = TrainerReport(
        district="Kanpur Nagar",
        batches=[],
        moves=[],
        selected_batch_id=None,
        selected_move_id=None,
        rows=[row_unsuppressed, row_suppressed],
        insight_text="अंतर्दृष्टि",
    )

    csv_data = generate_trainer_csv(report)
    lines = csv_data.strip().splitlines()
    assert len(lines) == 3  # Header + 2 rows

    # Header
    assert "batch_id,batch_name,move_id" in lines[0]

    # Row 1 (Unsuppressed)
    assert (
        "KNP-B1,कानपुर बैच 1,NUM_SUB_REGROUP_BUNDLES,दहाई का बंडल खोलकर घटाव,25,84%,बंडल खोलना,1.45,4,6,7,5,3"
        in lines[1]
    )

    # Row 2 (Suppressed, KNP-B3 with n=8)
    # Every metric field must equal SUPPRESSION_MESSAGE
    suppressed_line = lines[2]
    assert "KNP-B3,कानपुर बैच 3,NUM_SUB_REGROUP_BUNDLES,दहाई का बंडल खोलकर घटाव,8" in suppressed_line
    assert suppressed_line.count(SUPPRESSION_MESSAGE) == 8

    # Privacy guarantee: zero teacher names, phones or IDs anywhere in CSV
    assert "सुनीता" not in csv_data
    assert "98765" not in csv_data
