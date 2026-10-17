"""Unit tests for job scheduling arithmetic and message building (spec/08 §8.6, T24)."""

from datetime import UTC, date, datetime, timedelta

import pytest

from backend.app.core.messages import get_message, has_message
from backend.app.jobs import schedule
from backend.app.jobs.handlers import (
    FOLLOWUP_BUTTONS,
    HANDLERS,
    TEMPLATE_FOLLOWUP_QUESTION,
    _low_criteria,
    build_followup_messages,
)

# Wednesday 2026-10-14, 11:30 IST
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=UTC)


def test_ist_is_utc_plus_0530() -> None:
    assert schedule.to_ist(NOW).utcoffset() == timedelta(hours=5, minutes=30)
    assert schedule.to_ist(NOW).hour == 11
    assert schedule.to_ist(NOW).minute == 30


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError):
        schedule.next_daily_at(datetime(2026, 10, 14, 6, 0), 2)


def test_next_daily_at_rolls_to_next_day_after_the_hour() -> None:
    # 02:00 IST has passed today, so the next run is tomorrow 02:00 IST = 20:30 UTC today
    assert schedule.next_daily_at(NOW, 2) == datetime(2026, 10, 14, 20, 30, tzinfo=UTC)


def test_next_daily_at_is_strictly_after_now() -> None:
    exactly_two_ist = datetime(2026, 10, 13, 20, 30, tzinfo=UTC)
    assert schedule.next_daily_at(exactly_two_ist, 2) == datetime(2026, 10, 14, 20, 30, tzinfo=UTC)


def test_next_daily_at_later_today() -> None:
    assert schedule.next_daily_at(NOW, 17) == datetime(2026, 10, 14, 11, 30, tzinfo=UTC)


def test_next_weekly_at_saturday_1700_ist() -> None:
    assert schedule.next_weekly_at(NOW, schedule.SATURDAY, 17) == datetime(
        2026, 10, 17, 11, 30, tzinfo=UTC
    )


def test_next_weekly_at_after_slot_goes_to_following_week() -> None:
    saturday_evening = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)  # 17:30 IST
    assert schedule.next_weekly_at(saturday_evening, schedule.SATURDAY, 17) == datetime(
        2026, 10, 24, 11, 30, tzinfo=UTC
    )


def test_next_weekly_at_rejects_bad_weekday() -> None:
    with pytest.raises(ValueError):
        schedule.next_weekly_at(NOW, 7, 17)


def test_week_start_is_the_ist_monday() -> None:
    assert schedule.week_start_ist(NOW) == date(2026, 10, 12)
    # Sunday 23:00 UTC is already Monday in IST
    sunday_night_utc = datetime(2026, 10, 18, 23, 0, tzinfo=UTC)
    assert schedule.week_start_ist(sunday_night_utc) == date(2026, 10, 19)


def test_retry_delay_doubles_and_caps_at_one_hour() -> None:
    assert schedule.retry_delay(1, 60) == timedelta(seconds=60)
    assert schedule.retry_delay(2, 60) == timedelta(seconds=120)
    assert schedule.retry_delay(3, 60) == timedelta(seconds=240)
    assert schedule.retry_delay(20, 60) == timedelta(hours=1)
    with pytest.raises(ValueError):
        schedule.retry_delay(0, 60)


def test_truncate_words_never_splits_a_word() -> None:
    assert schedule.truncate_words("एक दो तीन चार", 2) == "एक दो"
    assert schedule.truncate_words("  एक   दो ", 5) == "एक दो"
    with pytest.raises(ValueError):
        schedule.truncate_words("एक", 0)


def test_followup_outside_window_uses_the_template() -> None:
    msgs = build_followup_messages(name="सुनीता", topic="दो कक्षाएँ", address_form="f", freeform=False)
    assert len(msgs) == 1
    assert msgs[0].kind == "template"
    assert msgs[0].template_name == TEMPLATE_FOLLOWUP_QUESTION
    assert msgs[0].template_params == ["सुनीता", "दो कक्षाएँ"]


def test_followup_inside_window_is_freeform_with_catalog_buttons() -> None:
    msgs = build_followup_messages(name="सुनीता", topic="दो कक्षाएँ", address_form="f", freeform=True)
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg.kind == "buttons"
    assert msg.text_hi == get_message(
        "followup_question", address_form="f", name="सुनीता", topic="दो कक्षाएँ"
    )
    expected = [(bid, get_message(key)) for bid, key in FOLLOWUP_BUTTONS if has_message(key)]
    assert [(b.id, b.title_hi) for b in msg.buttons] == expected
    assert 1 <= len(msg.buttons) <= 3


def test_low_criteria_handles_both_score_shapes() -> None:
    assert _low_criteria({"c2": 0, "c1": 2, "c3": 1}) == ["c2"]
    assert _low_criteria({"a": {"score": 0}, "b": {"score": 2}}) == ["a"]
    assert _low_criteria({"a": True, "b": None, "c": "0"}) == []


def test_handler_registry_covers_the_t24_kinds() -> None:
    assert set(HANDLERS) == {"followup_question", "arp_digest", "aggregates"}
