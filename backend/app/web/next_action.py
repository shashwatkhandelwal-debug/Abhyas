"""The one plain sentence above the composer: what to do now, from her saved session state.

Pure function of the state the chat already knows (onboarding stage, weekly state, setup stage, the
scene bar). The wording names the buttons the flow really offers (in her address form) and the
inputs it really accepts, and stays within two lines on a phone. It never reads a child's internal
state: in a scene it says what to ask, not how the child is doing.
"""

from __future__ import annotations

from typing import Any

from backend.app.core.messages import get_message
from backend.app.sessions.state_machine import OnboardingStateEnum, SessionStateEnum

# What the flow offers at each onboarding stage: (hint key, suggested line key or None)
ONBOARDING_HINTS: dict[str, tuple[str, str | None]] = {
    OnboardingStateEnum.JOIN_CODE.value: ("hint_join_code", "hint_join_code_suggest"),
    OnboardingStateEnum.PROFILE_NAME.value: ("hint_name", None),
    OnboardingStateEnum.PROFILE_ADDRESS.value: ("hint_address", None),
    OnboardingStateEnum.PROFILE_EXPERIENCE.value: ("hint_experience", "hint_experience_suggest"),
    OnboardingStateEnum.PROFILE_CLASSES.value: ("hint_classes", "hint_classes_suggest"),
    OnboardingStateEnum.SHARE_CONSENT.value: ("hint_share", None),
    OnboardingStateEnum.PLACEMENT_INTRO.value: ("hint_placement", "hint_placement_suggest"),
    OnboardingStateEnum.PLACEMENT.value: ("hint_placement", "hint_placement_suggest"),
}

# Weekly states whose step is one button or one spoken answer
WEEKLY_HINTS: dict[str, str] = {
    SessionStateEnum.LEARN.value: "hint_learn",
    SessionStateEnum.EXPLAIN_BACK.value: "hint_explain",
    SessionStateEnum.MODEL.value: "hint_model",
    SessionStateEnum.FEEDBACK.value: "hint_feedback",
    SessionStateEnum.TRY_IN_CLASS.value: "hint_try",
    SessionStateEnum.REFLECT_PEER.value: "hint_peer",
    SessionStateEnum.REFLECT_SELF.value: "hint_self",
    SessionStateEnum.DONE.value: "hint_done",
    SessionStateEnum.ASK.value: "hint_ask_more",
}

SETUP_STAGE_HINTS: dict[str, str] = {
    "choose_mode": "hint_choose_mode",
    "choose_child": "hint_choose_child",
}

EXAMPLE_KEYS = {
    "sub": "hint_example_sub",
    "add": "hint_example_add",
    "place_value": "hint_example_place_value",
    "read_word": "hint_example_read",
}


def _buttons(address_form: str) -> dict[str, str]:
    """The button labels the hints quote, in her address form (so the words match the buttons)."""
    names = {
        "agree": "btn_agree",
        "more": "btn_more",
        "yes": "btn_yes",
        "no": "btn_no",
        "understood": "btn_understood",
        "skip": "btn_skip",
        "listen": "btn_listen",
        "retry": "btn_retry",
        "continue": "btn_continue",
        "scene_continue": "btn_scene_continue",
        "peer": "btn_peer",
        "myself": "btn_self",
        "later": "btn_later",
        "next": "btn_next_move",
        "progress": "btn_progress",
    }
    return {name: get_message(key, address_form) for name, key in names.items()}


def _scene_example(scene: dict[str, Any] | None, child_name: str, address_form: str) -> str | None:
    """A line she can tap: how did you get your answer, with the board's own numbers."""
    item = (scene or {}).get("item")
    if not item:
        return None
    key = EXAMPLE_KEYS.get(str(item.get("type")))
    if key is None:
        return None
    return get_message(key, address_form, child=child_name, a=item.get("a"), b=item.get("b"))


def _concrete_example(
    scene: dict[str, Any] | None, child_name: str, address_form: str
) -> str | None:
    """A line that brings in something concrete, using the number on the board."""
    item = (scene or {}).get("item") or {}
    if item.get("type") not in ("sub", "add") or item.get("a") is None:
        return None
    return get_message("hint_example_concrete", address_form, child=child_name, a=item["a"])


def _make(
    key: str,
    address_form: str,
    suggest: str | None = None,
    step: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """`key` is the catalogue key; `step` (default: the key) is what she dismisses by sending."""
    text = get_message(key, address_form, **_buttons(address_form), **extra)
    return {"key": step or key, "text": text, "suggest": suggest}


def next_action(
    *,
    onboarding: str,
    state: str,
    context: dict[str, Any],
    retries: int,
    address_form: str,
    started: bool,
    scene: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """{"key", "text", "suggest"} for this moment, or None when there is nothing to say."""
    af = address_form or "f"
    if onboarding != OnboardingStateEnum.READY.value:
        if onboarding == OnboardingStateEnum.NEW.value:
            if not started:
                return _make("hint_start", af, get_message("hint_start_suggest", af))
            return _make("hint_consent", af)
        entry = ONBOARDING_HINTS.get(onboarding)
        if entry is None:
            return None
        key, suggest_key = entry
        return _make(key, af, get_message(suggest_key, af) if suggest_key else None)

    # Questions she is in the middle of answering come before the weekly step
    if context.get("awaiting_delete_confirm"):
        return _make("hint_delete", af)
    for stage_field, ask_key in (
        ("class_stage", "hint_class_ask"),
        ("skill_stage", "hint_skill_ask"),
    ):
        stage = context.get(stage_field)
        if stage == "asking":
            return _make(ask_key, af)
        if stage == "confirm":
            return _make("hint_confirm", af)
    if context.get("checkin_stage") in ("module", "outcome", "struggle") or context.get(
        "level_stage"
    ) in ("subject", "count"):
        return _make("hint_checkin", af)
    rating = context.get("rating_stage")
    if state == SessionStateEnum.DONE.value and rating:
        return _make("hint_rating" if rating == "rating" else "hint_rating_comment", af)
    if (
        state == SessionStateEnum.FEEDBACK.value
        and context.get("module_mode")
        and context.get("module_check_stage") == "asking"
    ):
        return _make("hint_module_check", af)
    if state == SessionStateEnum.FEEDBACK.value and context.get("resume_scene_id"):
        return _make("hint_too_short", af)

    if state in (SessionStateEnum.REHEARSE_INTRO.value, SessionStateEnum.REHEARSE.value):
        return _practice_hint(context, retries, af, scene)
    weekly_key = WEEKLY_HINTS.get(state)
    return _make(weekly_key, af) if weekly_key else None


def _practice_hint(
    context: dict[str, Any], retries: int, af: str, scene: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Setup stages, then the scene: what to ask first, then how to keep going.

    The wording follows her own turn count only (never a child's state); she dismisses it for the
    whole scene by sending a line, so the first and the "keep going" texts share one step key.
    """
    stage = str(context.get("rehearse_stage", ""))
    if stage in SETUP_STAGE_HINTS:
        return _make(SETUP_STAGE_HINTS[stage], af)
    mode = str(context.get("rehearse_mode", ""))
    one_on_one = bool(scene and scene.get("mode") == "one_on_one") or mode == "one_on_one"
    spoken = int((scene or {}).get("turn", 0)) >= 1
    if one_on_one:
        child = str((scene or {}).get("child_name") or "")
        if stage == "diagnose":
            return _make("hint_diagnose", af, child=child)
        if spoken:
            return _make(
                "hint_scene_one_next",
                af,
                _concrete_example(scene, child, af),
                step="scene_one",
                child=child,
            )
        suggest = _scene_example(scene, child, af)
        key = "hint_retry_one" if retries > 0 else "hint_scene_one"
        return _make(key, af, suggest, step="scene_one", child=child)
    if spoken:
        return _make("hint_scene_group_next", af, step="scene_group")
    children = (scene or {}).get("children") or []
    first = str(children[0]["name"]) if children else ""
    suggest = _scene_example(scene, first, af) if first else None
    key = "hint_retry_group" if retries > 0 else "hint_scene_group"
    return _make(key, af, suggest, step="scene_group")
