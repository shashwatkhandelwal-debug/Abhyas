"""Experience-aware start: [सीधे अभ्यास] for the higher onboarding bands, key points kept."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from test_class_checkin import Teacher, ids

from backend.app.channels.whatsapp.buttons import plan_buttons
from backend.app.class_profile import fast_start
from backend.app.config import settings
from backend.app.core.messages import get_message, reset_ui_lang, set_ui_lang
from backend.app.core.types import OutboundMessage
from backend.app.rehearsal.scene_runner import load_move_card
from backend.app.sessions import rehearse_setup
from backend.app.sessions.state_machine import SessionStateEnum

DASHES = ("—", "–")
MOVE = "NUM_SUB_REGROUP_BUNDLES"


@pytest.fixture(autouse=True)
def flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "FAST_START_ENABLED", True)


@pytest.fixture(params=["hi", "en"])
def lang(request: pytest.FixtureRequest) -> Iterator[str]:
    token = set_ui_lang(request.param)
    yield request.param
    reset_ui_lang(token)


async def teacher_with_band(band: str | None, move: str = MOVE) -> Teacher:
    t = await Teacher("demo3", "f").setup()
    ctx = await t.ctx()
    ctx.experience_band = band
    ctx.first_year = band == "0-1"
    ctx.current_move_id = move
    ctx.current_state = SessionStateEnum.LEARN
    await t.service._sync_context_to_db(ctx, t.teacher_id)
    return t


async def learn(t: Teacher, move: str = MOVE) -> list[OutboundMessage]:
    return await t.service.start_module(t.teacher_id, move)


def text_of(out: list[OutboundMessage]) -> str:
    return "\n".join(m.text_hi or "" for m in out)


@pytest.mark.asyncio
@pytest.mark.parametrize("band", ["0-1", "2-5", None])
async def test_below_threshold_no_option_and_model_practice_stays_first(
    band: str | None, lang: str
) -> None:
    t = await teacher_with_band(band)
    out = await learn(t)
    assert fast_start.BTN_FAST not in ids(out)
    assert get_message("fast_start_note") not in text_of(out)
    assert set(ids(out)) == {"btn_understood", "btn_replay"}
    await t.tap(fast_start.BTN_FAST)  # a stale tap does nothing for her
    assert (await t.ctx()).current_state == SessionStateEnum.LEARN
    await t.tap("btn_understood")  # the usual loop: explain back, then the model
    assert (await t.ctx()).current_state == SessionStateEnum.EXPLAIN_BACK


@pytest.mark.asyncio
@pytest.mark.parametrize("band", ["6-10", "10+"])
async def test_above_threshold_the_option_and_the_note_appear(band: str, lang: str) -> None:
    t = await teacher_with_band(band)
    out = await learn(t)
    assert ids(out) == ["btn_understood", "btn_replay", fast_start.BTN_FAST]
    assert get_message("fast_start_note") in text_of(out)
    plan = plan_buttons(out[-1].buttons or [], has_audio=False)
    sent = [b for b, _ in plan.reply_buttons]  # replay is only offered with audio
    assert fast_start.BTN_FAST in sent and len(sent) <= settings.WHATSAPP_REPLY_BUTTONS_MAX
    assert plan.list_rows == []


@pytest.mark.asyncio
async def test_choosing_it_opens_the_setup_and_keeps_the_key_points(lang: str) -> None:
    t = await teacher_with_band("6-10")
    await learn(t)
    out = await t.tap(fast_start.BTN_FAST)
    ctx = await t.ctx()
    assert ctx.current_state == SessionStateEnum.REHEARSE_INTRO
    assert ctx.rehearse_stage == rehearse_setup.STAGE_CHOOSE_MODE
    assert out[-1].text_hi == get_message("rehearse_mode_prompt", "f")
    assert ids(out) == [rehearse_setup.BTN_ONE, rehearse_setup.BTN_GROUP, fast_start.BTN_KEYPOINTS]
    # the key points are reachable and the mode choice stays on screen
    kp = await t.tap(fast_start.BTN_KEYPOINTS)
    move = load_move_card(MOVE)
    english = lang == "en"
    first_point = (
        (move.key_points[0].text_en or move.key_points[0].text_hi)
        if english
        else (move.key_points[0].text_hi)
    )
    assert get_message("fast_keypoints_head") in text_of(kp) and first_point in text_of(kp)
    assert rehearse_setup.BTN_ONE in ids(kp) and fast_start.BTN_KEYPOINTS in ids(kp)
    assert (await t.ctx()).rehearse_stage == rehearse_setup.STAGE_CHOOSE_MODE
    out = await t.tap(rehearse_setup.BTN_GROUP)  # and the practice goes on as usual
    assert (await t.ctx()).rehearse_stage == rehearse_setup.STAGE_SCENE and out


@pytest.mark.asyncio
async def test_group_only_move_gets_a_key_points_button_on_its_intro() -> None:
    t = await teacher_with_band("10+", move="LIT_MATRA_BLENDING")
    out = await t.service._build_learn_messages(
        load_move_card("LIT_MATRA_BLENDING"), "f", [], experience_band="10+"
    )
    assert fast_start.BTN_FAST in ids(out)
    out = await t.tap(fast_start.BTN_FAST)
    assert (await t.ctx()).current_state == SessionStateEnum.REHEARSE_INTRO
    assert ids(out) == [fast_start.BTN_KEYPOINTS]


@pytest.mark.asyncio
async def test_key_points_carry_their_stored_sources() -> None:
    t = await teacher_with_band("6-10", move="NUM_COMPARE_BUNDLES")
    ctx = await t.ctx()
    ctx.current_state = SessionStateEnum.REHEARSE_INTRO
    await t.service._sync_context_to_db(ctx, t.teacher_id)
    out = await t.tap(fast_start.BTN_KEYPOINTS)
    assert get_message("fast_keypoints_sources", sources="").split("{")[0].strip() in text_of(out)


@pytest.mark.asyncio
async def test_progress_marks_the_learn_step_as_skipped() -> None:
    skipped = await teacher_with_band("6-10")
    await learn(skipped)
    await skipped.tap(fast_start.BTN_FAST)
    ctx = await skipped.ctx()
    assert ctx.checkin_jump_move == MOVE  # the marker a check-in jump to practice leaves too
    await skipped.service._track_module_progress(skipped.teacher_id)
    assert not any(p.learn_done_at for p in skipped.repo._module_progress.values())
    # the same move reached the usual way marks the learn step done
    usual = await teacher_with_band("2-5")
    ctx = await usual.ctx()
    ctx.current_state = SessionStateEnum.REHEARSE_INTRO
    await usual.service._sync_context_to_db(ctx, usual.teacher_id)
    await usual.service._track_module_progress(usual.teacher_id)
    assert any(p.learn_done_at for p in usual.repo._module_progress.values())


@pytest.mark.asyncio
async def test_flag_off_no_option_and_the_tap_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    t = await teacher_with_band("10+")
    monkeypatch.setattr(settings, "FAST_START_ENABLED", False)
    out = await learn(t)
    assert fast_start.BTN_FAST not in ids(out) and get_message("fast_start_note") not in text_of(
        out
    )
    await t.tap(fast_start.BTN_FAST)
    assert (await t.ctx()).current_state == SessionStateEnum.LEARN
    assert not fast_start.eligible("10+")


def test_texts_in_both_languages_without_dashes_and_titles_fit() -> None:
    for code in ("hi", "en"):
        for key in (
            "fast_start_note",
            "btn_fast_start",
            "btn_fast_keypoints",
            "fast_keypoints_head",
        ):
            text = get_message(key, lang=code)
            assert text and not any(d in text for d in DASHES), key
        for key in fast_start.ALL_BUTTONS:
            assert len(get_message(key, lang=code)) <= settings.WHATSAPP_BUTTON_TITLE_MAX
    assert get_message("fast_start_note", lang="hi") == (
        "आपके अनुभव के हिसाब से आप सीधे अभ्यास से शुरू कर सकते हैं; मुख्य बातें कभी भी देख सकते हैं।"
    )
    assert get_message("btn_fast_start", lang="hi") == "सीधे अभ्यास"
    assert get_message("btn_fast_keypoints", lang="hi") == "मुख्य बातें देखें"
    _: Any = None
