# fix7 report

Branch `fix7`, cut from `main` (4684eab). Not merged.

## 1. Guide answer keeps the step's buttons (steps 5, 6, 7)

Cause: after a Guide answer the "Let's carry on" message was always plain text, so the step's quick replies were gone.

Fix (`backend/app/sessions/service.py`): the carry-on message is now built by `_resume_message`, which re-sends the step's own buttons.

| Step | State | Buttons after the Guide answer |
|---|---|---|
| 5 | FEEDBACK | Practise again / Continue / My progress (My progress only when the flag is on, as elsewhere) |
| 6 | TRY_IN_CLASS | Peer observed / I'll tell it myself / Later |
| 7 | REFLECT_PEER | Yes / No |
| 7 | REFLECT_SELF | none (free-text answer step) |

Also at step 7: the carry-on text showed the raw catalogue placeholders (`({i}/{n}): {item}`, `{i}: {question}`). It now fills in the item or question she was on.

Typed `continue` (any case, trailing `.` or `!`) at step 5 now works as the Continue button; `next` already did.

Tests: `backend/tests/integration/test_fix7_resume_buttons.py` runs on the real seeded `teacher.demo2` chat (Hindi and English question, steps 5, 6, 7 peer, 7 self; typed continue/Continue/next/Next). It also asserts no `{` in the carry-on text, and that the state is unchanged.

## 2. Log out on offline.html

`offline.html` has a Log out link (Hindi and English) to `/logout`, the same path as the other pages. A click first empties every store of `abhyas_chat_db` (same pattern as `progress.html`), then goes to `/logout`. A 1.5 s timer goes anyway if IndexedDB is slow or blocked. If the database was never created, nothing is created. The next account therefore never sees a cached chat. Test: `test_offline_page_has_a_logout_that_empties_the_chat_cache`.

## Payload

`scripts/check_first_load.py`: first load 130,189 B, all assets 152,573 B, **headroom 1,027 B** (limit 153,600 B; must stay above 1,000 B). Before the change it was 1,663 B. The first version of the inline script cost 636 B of headroom, left 738 B, and had to be compacted. Headroom is thin: the next asset change needs savings elsewhere.

## Gates

- ruff check clean; mypy --strict clean (203 files); my files are `ruff format` clean (14 other files in the repo were already not formatted before this change).
- node tests: 121 pass.
- pytest unit + integration against a migrated database: pass. The first run had 98 failures, all `column "class_struggles" of relation "teacher" does not exist`. That was the local `postgres` test database with a stale schema, not this change. Re-running those files against a freshly migrated database: all pass.
- Not run: browser e2e (Playwright), `make test-live`.
