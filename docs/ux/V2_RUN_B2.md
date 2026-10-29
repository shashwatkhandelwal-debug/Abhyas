# V2 Run B2 report

Branch `feat/v2-national`. Nothing merged or deployed; no Anthropic API calls; rule engine, guards, auth and composer layout untouched.

## What I ran (and its result)
- `ruff check .`: All checks passed. `mypy --strict backend/app`: no issues in 172 source files.
- `python scripts/check_first_load.py`: teacher chat 127.7 KB raw / 30.5 KB gzip, offline assets 148.34 KB, PASS (< 150 KB). It rewrote `eval/lowband/REPORT.md`, which was already modified before this run; I left it uncommitted.
- Full gate once: `python scripts/pytest_fresh_db.py --server postgresql://postgres:postgres@127.0.0.1:5432/postgres` (abhyas-db-1, port 5432, no earlier pytest running): **1903 passed, 1 skipped in 721.83s**. The skip is `test_evaluator_samples.py:79` (no sample audio on disk, needs SARVAM_API_KEY). Raw log: `%TEMP%\gate_b2.log`.
- Assumed, not run: hosted deploy behaviour, real WhatsApp delivery (Meta limits are from the Cloud API docs/code comments, not exercised live), a real browser session of the in-scene chip.

## Task 1: channel-specific button caps
- Before: the 3-button / 20-char limits were constants in `channels/whatsapp/client.py` (`MAX_BUTTONS_COUNT`, `MAX_BUTTON_TITLE_LENGTH`) and a hard-coded `<= 3` in `channels/whatsapp/channel.py`; the check-in flow capped at `CHECKIN_MAX_BUTTONS = 5` for every channel, and `Button.title_hi` was limited to 20 for every channel.
- Now (`backend/app/config.py`): `CHECKIN_MAX_BUTTONS=5` (web), `WEB_BUTTON_TITLE_MAX=40`, `WHATSAPP_REPLY_BUTTONS_MAX=3`, `WHATSAPP_BUTTON_TITLE_MAX=20`, `WHATSAPP_LIST_ROWS_MAX=10`.
- Which channel uses which cap: `WebChannel.send` (`channels/web.py`) persists `msg.buttons` unchanged, so web shows up to 5 and keeps titles as written. `WhatsAppChannel.send` calls `plan_buttons` (`channels/whatsapp/buttons.py`): at most 3 reply buttons, otherwise one interactive list (existing `send_interactive_list`); titles cut to 20 there only. The client enforces the same limits again.
- Tests: `backend/tests/unit/test_button_channel_caps.py` (5-option check-in screen: 5 on web, 0 reply buttons and 5 list rows on WhatsApp; 1-3 stay reply buttons; long titles shortened on WhatsApp only; Graph payloads respect the limits).
- Limit: a list longer than 10 rows is cut by the client; no screen in the repo exceeds 5.

## Task 2: check-in from inside a scene (no engine change)
- The chip now shows when a scene is active (`web/teacher.py`, `active_scene` condition removed; flag still controls it). Tapping it pauses the scene by not touching it: only `checkin_*` context fields change.
- Results inside a scene offer **वापस अभ्यास पर** (`btn_chk_resume`) instead of "Practise with Ravi" (that would replace the scene), plus "Ask the handbook" (the existing ASK flow already returns to REHEARSE). "It went well" also ends with the resume button. Resume replies with the existing `ask_resume_scene_*` line. New catalog keys in hi and en: `btn_chk_resume`, `chk_in_scene_practice`, `chk_scene_waiting`.
- Decisions: typed words in a scene are never a check-in command; typing while a check-in is open inside a scene drops the unfinished check-in (nothing stored) so the scene cannot appear frozen. The setup screen (`REHEARSE_INTRO`, choosing a child) still ignores the entry.
- Known behaviour, unchanged: with the flag off a stray `btn_chk_start` tap is routed like any unknown button; the chip is not rendered then.
- Tests (`test_class_checkin.py`): demo2 scene landing reaches the outcome screen in 2 taps; scene fields identical before and after (state, move, mode, child, turns, retries, diagnosis); resume text; went-well path; handbook returns to the scene; typing; stale resume button; flag off (no chip, no check-in); page test with an active scene shows the chip, flag off hides it.

## Task 3: Run B migration (fresh DB `abhyas_test_mig_b2`, port 5432, dropped afterwards)
```
alembic heads            -> e9b1d3f5a7c2 (head)
alembic upgrade head     -> ... c4e6a8b0d2f3 -> e9b1d3f5a7c2, Add class_checkin table ; current: e9b1d3f5a7c2 (head)
alembic downgrade -1     -> Running downgrade e9b1d3f5a7c2 -> c4e6a8b0d2f3 ; current: c4e6a8b0d2f3
alembic upgrade head     -> Running upgrade c4e6a8b0d2f3 -> e9b1d3f5a7c2 ; current: e9b1d3f5a7c2 (head)
alembic heads            -> e9b1d3f5a7c2 (head)
```
Single head. Coverage: existing `test_alembic_migrations_round_trip` (base round trip, checks `class_checkin` columns, constraint, FK, index) plus the new `test_single_head_and_last_migration_steps_back_and_forward` in `backend/tests/integration/test_migrations.py`.

## Task 4
`docs/EVALUATOR_GUIDE.md`: new "After-class check-in" section (demo2 four taps and the resume button, demo3 practice that skips the learn step, WhatsApp list split) and a step in the suggested hour.

## Commits
```
65b0e38 T-B2.1: per-channel button caps (web 5, WhatsApp 3 reply buttons / 20-char titles, list overflow)
 backend/app/channels/whatsapp/buttons.py       | 39 ++++++++++++
 backend/app/channels/whatsapp/channel.py       | 18 ++----
 backend/app/channels/whatsapp/client.py        | 11 ++--
 backend/app/class_profile/checkin_flow.py      |  8 +--
 backend/app/config.py                          |  6 +-
 backend/app/core/types.py                      | 10 ++-
 backend/tests/unit/test_button_channel_caps.py | 87 ++++++++++++++++++++++++++
 7 files changed, 153 insertions(+), 26 deletions(-)
```
```
12f1c4c T-B2.2: check-in reachable inside a running scene (pause, resume via 'back to practice')
 backend/app/class_profile/checkin_flow.py |  45 ++++++--
 backend/app/sessions/service.py           |   3 +
 backend/app/web/teacher.py                |   3 +-
 backend/tests/unit/test_class_checkin.py  | 170 +++++++++++++++++++++++++++++-
 content/messages_en.yaml                  |   3 +
 content/messages_hi.yaml                  |   3 +
 6 files changed, 213 insertions(+), 14 deletions(-)
```
```
f1f817d T-B2.3: test single alembic head and one-step downgrade/upgrade of class_checkin
 backend/tests/integration/test_migrations.py | 36 ++++++++++++++++++++++++++++
 1 file changed, 36 insertions(+)
```
```
a30d3a2 T-B2.4: evaluator guide: after-class check-in taps, practice skips learn, WhatsApp list overflow
 docs/EVALUATOR_GUIDE.md | 28 +++++++++++++++++++++++++---
 1 file changed, 25 insertions(+), 3 deletions(-)
```
