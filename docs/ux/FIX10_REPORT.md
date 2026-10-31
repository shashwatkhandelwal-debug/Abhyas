# FIX10 report

Base: main at 10052cf. Branch: `fix10`. Template, CSS and test changes only. No seed, migration or data changes. `offline.html`, `sw.js`, `chat.js` and `app.css` are untouched.

## 1. /review/calibrate: empty demo turns
File: `backend/app/web/templates/review_calibrate.html`

- A turn whose text is empty or whitespace now shows, inside its bubble, the muted line (Hindi, then English): "No text stored for this demo turn."
- If every turn is empty, one line appears above the transcript (Hindi, then English): "This is demo data, so the conversation text is not stored. For a real practice, it appears here."
- The muted text colour is `#4A524E` on the light teacher bubble `#E4EFEA` (about 6.8:1). In dark theme it is `#C4CCC8` on `#194D40` (about 5.8:1). The line above the transcript uses `--muted` on `--surface` (about 5.9:1 light, 7:1 dark). All are above 4.5:1. The ratios are hand-computed, not measured with a tool.
- The scoring form is unchanged.
- The text is inline in the template rather than in the message catalog, to keep this to template text only.

## 2. Trainer table: suppressed (n<10) cell
File: `backend/app/web/templates/trainer.html`

- Dark theme only (`prefers-color-scheme: dark`): cell background `#2A1B1B`, badge background `#3A1F1F`, text `#FFB4AB` (about 9:1 on the badge), thin dashed border `#A55A55`, and compact padding so the row is no taller than a data row. The light-theme look is unchanged.
- The batch column has `min-width: 11rem`, and the batch name sits on its own line below the batch id, so it no longer wraps one word per line.
- The n value and the privacy rule are unchanged.

## Tests
- New unit tests in `backend/tests/unit/test_review_console.py`:
  - All turns empty: placeholder shown 3 times, demo line shown, form fields still present.
  - Mixed turns: placeholder shown once, demo line absent.
- Node tests: 122/122 pass.
- `ruff check .` passes. `mypy --strict backend/app` passes.
- pytest: `test_review_console`, `test_trainer_report`, `test_chat_ux_assets` (asset budget), `test_check_first_load` pass. `test_review_console_integration` is skipped because `TEST_DATABASE_URL` is not set.
- `ruff format --check .` reports 14 files that were already unformatted at 10052cf. I did not touch them. The file I edited is formatted.

## Not verified
- Not checked visually in a browser.
