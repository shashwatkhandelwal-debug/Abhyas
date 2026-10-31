# FIX8 report

Branch `fix8`, from main `fc68ea1`. Fixes only. No seed, migration or content-data change. `offline.html`, `sw.js`, `chat.js` and `app.css` (which is in the offline payload) are untouched.

## What changed

1. **Badges (arp, trainer, review).** `.badge-support` had the light dark-theme ink on a fixed light background. `arp.html` now has dark-theme colours for `.badge-support` (#E3ECF6 on #2B3A4D, 9.7:1), `.badge-help` (#FFB4AB on #5A1A16) and `.badge-ok` (#9BE0CB on #19382E, 8.5:1). Light theme unchanged. `/trainer` has no `badge-*` class. `/review` `.badge-count` and `.badge-alert` use fixed colours that already pass (5.1:1 and 5.6:1) in both themes.
2. **Links.** `_dash_css.html` (shared by arp, trainer and review only) styles in-page links: #1F6F5C in light, #7FD0B9 in dark (8.7:1 on the card surface), underline kept. This covers "Open the printable agenda", "See the card" and the CSV links. The card page `trainer_move.html` got the same rule for its back link.
3. **Trainer privacy wording.** `ui_trainer_class_desc` and `ui_trainer_skills_desc`, Hindi and English, now end: "Shown only when at least 10 consenting teachers answered." (Hindi: "केवल तभी दिखता है जब सहमति देने वाले कम से कम 10 शिक्षकों ने उत्तर दिया हो।"). The numbers are unchanged. README Privacy gains the same sentence as a bullet. The arp page and the agenda did not carry the "hidden below 10" wording, so nothing to change there.
4. **Coach review empty state.** `ui_review_no_transcript`, Hindi and English, now: "This is demo data, so no transcript is stored. For a real practice, the conversation appears here." Data untouched.

## Skipped, and why

- Everything the sweep found beyond items 1 and 2 (below): you asked for report only.
- `app.css` is in the service-worker payload, so shared colours (`--brand` on dark) were not changed there.
- `docs/EVALUATOR_GUIDE.md` line about training ratings "hidden below 10 ratings" left as is: it is about ratings, not the two lists.

## Checks

- node tests: chat 82, idb 17, sw 22, all pass.
- ruff check: clean. mypy --strict: clean.
- `scripts/check_first_load.py` (asset budget): PASS, 127.14 KB first load, 149.0 KB all offline assets, offline payload unchanged. (It rewrites `eval/lowband/REPORT.md`; I reverted that.)
- pytest, only files touching the changed messages/templates: dash_free, coach, chat_ux_assets, class_struggles, teaching_skills, fix5_dashboard_css, fix6_privacy_and_guide_gap, dashboard_labels, review_console, messages_loader, messages_en, test_chat_js_dedup, test_js_harness, test_speech_budget: pass.
- Not clean, unrelated to this change: `ruff format --check` lists 14 existing .py files; `test_support_framing.py` fails identically on unmodified main here (`cluster_pack.py:108`, coroutine not iterable). Not investigated.

## Contrast sweep (report only)

Method: headless Chromium (390px wide), seeded demo data on a fresh local DB, computed colour of every visible text node against its effective background, WCAG 4.5:1 (3:1 for large text), both themes. Pages: login, arp, arp agenda, trainer, trainer card, trainer agenda, review (4 tabs), review item, review calibrate, teacher start/class/delete/modules/progress. 1180 pairs checked.

**Light theme: 0 failures. Dark theme: 84 failing pairs**, grouped:

| Theme | Text | Background | Ratio | Where |
|---|---|---|---|---|
| dark | rgb(240, 237, 232) | rgb(228,239,234) | 1.01 | /review/calibrate `div` |
| dark | rgb(28, 31, 29) | rgb(20,24,22) | 1.08 | /trainer/move/LIT_MATRA_BLENDING `h1`; /trainer/move/LIT_MATRA_BLENDING `h2`; /trainer/move/LIT_MATRA_BLENDING `li`; /trainer/move/LIT_MATRA_BLENDING `p` |
| dark | rgb(155, 28, 28) | rgb(30,36,33) | 1.94 | /trainer `td` |
| dark | rgb(179, 38, 30) | rgb(30,36,33) | 2.42 | /teacher/delete `h1.delete-dialog-title`; /teacher/progress `a.btn-delete-link`; /teacher/progress `h2.section-heading.danger` |
| dark | rgb(31, 111, 92) | rgb(30,36,33) | 2.62 | /arp `button.btn-print`; /arp `div.stat-val`; /arp `summary`; /review/calibrate `h2` (+14 more) |
| dark | rgb(31, 111, 92) | rgb(20,24,22) | 2.97 | /arp `a.lang-link.active`; /arp `a.lang-link`; /arp `h1`; /arp `summary` (+17 more) |

Causes: `--brand` (#1F6F5C) is not lightened in dark in `app.css` (headings, lang links, tabs, stat values, buttons, chips); `--danger` the same; `/trainer/move/*` uses an undefined `--text` variable so its text stays dark; `/review/calibrate` bubbles use a light bubble background with light ink; `/trainer` suppression cells use a fixed #9B1C1C.

Not covered: the teacher chat page itself (`/teacher` showed the chat shell only), `/admin`, `waking.html`, error pages.
