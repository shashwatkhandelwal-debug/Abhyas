# Run report 2 (branch `feature/hackathon-polish`)

Start HEAD `89ae6d8`. Everything below is from commands run in this session unless marked **(assumed)**.
Transcripts are condensed only by putting the three child states of a turn on one line.

## Results at a glance

| Task | Result |
|---|---|
| 1 scene_store + 4th turn | Both Step 3 changes were test-environment workarounds. Reverted; the test is fixed properly; the behaviour is pinned. Commits `e004030`, `0b5eb1b`, `f5667cb`. |
| 2 payload reconciliation | Local number (151,632 B) is inflated by CRLF working-tree files. Linux/LF number is **149,340 B**. Step 3's 153,231 B is **not reproducible**. Real seeded `/teacher` HTML is ~5.9 KB larger than the script measures. |
| 3 full suite | pytest **1566 passed, 129 skipped, 0 failed, 0 errors**; node **65 pass, 0 fail**. |
| 4 literacy script | The one-turn shift is a **script difference**, not the tagger fix and not the engine. The tagger fix is visible in a different place (Turn 2/3 active word). |
| 5 Chip C / A1 / A2 / B | Chip C is NOT a curated handbook chip; it goes through the LLM classifier. Citation chip renders (1). `ANTHROPIC_API_KEY` is set; A1/A2/B tagged 3x each, stable. |

## Mistakes in this run (read first)

- **Commit `0b5eb1b` left `test_score_sharing_consent` failing** on a machine with Postgres up. I chained the
  commit after `tail -1` and did not read "1 failed". Fixed by `f5667cb`. Do not cherry-pick `0b5eb1b` alone.
- An earlier-in-session claim "everything passes with both Step 3 changes reverted" was wrong: I had only read the
  last 5 lines of a `-qq` run. The truth is in Task 1.
- My first "HEAD" payload run actually ran inside the `dda0af9` worktree (parallel calls shared one shell). It was
  discarded; the HEAD numbers below come from a rerun with the main tree.

## Task 1: scene_store.py and the fourth teacher turn

### Exact diff of Step 3 (`dda0af9`)

```diff
--- a/backend/app/rehearsal/scene_store.py   (PostgresSceneStore.get_active_for_teacher)
                 if active_id is not None:
                     return await self.get(active_id)
-                return None
+                return await self._memory.get_active_for_teacher(teacher_id)
--- a/backend/tests/unit/test_score_sharing_consent.py
+    # Turn 4 (satisfies MIN_TURNS_FOR_COACH_GROUP = 3 in scene)
+    await service.handle_inbound(_inbound(t_id, text="अब बताओ कुल कितनी तीलियाँ हुईं?"))
```

### What required them (verified)

- `DATABASE_URL` defaults to `postgresql+asyncpg://postgres:postgres@localhost:5432/abhyas` (config.py:34), so
  the `scene_store` singleton is a `PostgresSceneStore` in unit tests whenever a local Postgres answers
  (confirmed: `type(scene_store).__name__ == PostgresSceneStore`).
- `test_score_sharing_consent` uses fake teachers with no Postgres row. Saving the scene fails with
  `ForeignKeyViolationError` (seen in the log) and is swallowed. Then Postgres says "no active scene", so without
  the Step 3 fallback the scene "vanishes": the test saw buttons `['btn_scene_continue','btn_skip']` instead of
  `btn_share_arp`.
- Run matrix, Postgres reachable, test file only:
  - `7f699b4` (before Step 3, worktree): **1 failed, 4 passed**. So it was already failing before Step 3 on such a machine
    (the failing assertion there was not inspected; same cause **assumed**).
  - `dda0af9` (worktree): 5 passed.
  - HEAD with the fallback reverted and no 4th turn, no isolation fix: 1 failed (`btn_share_arp` missing).
  - HEAD with the fallback reverted and no 4th turn but an in-memory store fixture: **5 passed** (`f5667cb`).
- The 4th turn was **not needed**: with the fallback present, 3 turns passed (5 passed). It was cargo.
- No runnable test needed the fallback: the Postgres-gated reset/scene tests (`test_demo_reset_postgres.py` 14 +
  `test_scene_runner.py`, run against the local pgvector with `TEST_DATABASE_URL`, fixture creates its own throwaway
  DB) gave **17 passed, 1 skipped** with the fallback reverted.
- Whether the UI work needs it: no.

### What the fallback changes in production (Postgres + `DATABASE_URL` set)

- Triggers when Postgres answers successfully and has **no active row** for the teacher; then it returns
  whatever this process's in-memory dict holds for that teacher.
- It **can resurrect** an ended scene. `reset_demo_teacher` (runs on every demo login/logout) deletes the DB scene
  rows, and nothing in the app clears the process-local store (grep: no `scene_store.clear`/`_memory` use outside
  the store). A unit test with a simulated "DB has no active row" shows the cached scene coming back
  (`test_db_answers_no_active_scene_so_cached_active_scene_is_not_resurrected` **fails** with the fallback restored).
  I did **not** reproduce this end to end over HTTP; that it happens after a real demo reset is inferred from the code.
- It **can hide a lost scene**: if a Postgres write fails (swallowed, logged as a warning), the fallback keeps the
  conversation going from memory in that process. That is the one upside; it also masks the failure.
- "Can two sessions share state?" The cache is keyed by `teacher_id`, per process. Two sessions on the same teacher
  (the shared demo logins) already share that teacher's DB state; they would additionally share a stale cached scene
  after a reset. Different teachers never share. With more than one worker the caches differ per worker, so behaviour
  would depend on which worker answers **(assumed: worker count not checked)**.

### Commits

- `e004030` revert the fallback + add `test_scene_store_active_lookup.py` (2 tests: "DB says none -> None";
  "DB unreachable -> cached scene still used").
- `0b5eb1b` revert the 4th turn (left the test failing with Postgres up, see above).
- `f5667cb` autouse fixture giving the test an `InMemorySceneStore` (patches `scene_store` in `sessions.service` and
  `rehearsal.scene_runner`, the module the service's `SceneRunner()` reads).

Other unit tests may share the same "reachable local Postgres" sensitivity; the full run in Task 3 had Postgres up
and passed, and I did not hunt for more.

## Task 2: payload reconciliation

### Raw outputs of `scripts/check_first_load.py` (worktree = temporary `git worktree`, no checkout)

At `dda0af9` (worktree `.wt/s3`, LF files):
```
Teacher Chat First-Load: 125.2 KB raw / 29.75 KB gzip
All Offline Assets: 145.84 KB raw / 36.97 KB gzip
Status: PASS (< 150 KB)
exact: teacher 128203 B, all 149340 B, headroom 4260 B (limit 153600)
```
At HEAD `f5667cb` (main working tree, CRLF chat.js/recorder.js/sw.js):
```
Teacher Chat First-Load: 127.44 KB raw / 29.87 KB gzip
All Offline Assets: 148.08 KB raw / 37.09 KB gzip
Status: PASS (< 150 KB)
exact: teacher 130495 B, all 151632 B, headroom 1968 B
```

### Bytes per file (script)

| File | dda0af9 worktree | HEAD main tree | Diff | Cause |
|---|---|---|---|---|
| /login | 5,979 | 5,979 | 0 | |
| /teacher (empty mock state) | 20,607 | 20,607 | 0 | |
| manifest.json | 514 | 514 | 0 | |
| ack.js | 1,097 | 1,097 | 0 | |
| app.css | 35,484 | 35,484 | 0 | LF in both |
| **chat.js** | 65,680 | 67,763 | **+2,083** | 2,083 lines, all CRLF in main tree |
| **recorder.js** | 5,918 | 6,127 | **+209** | 209 lines, CRLF |
| sw.js (served) | 4,207 | 4,207 | 0 | server reads it as text (CRLF -> LF, stamp substituted) |
| offline.html | 9,854 | 9,854 | 0 | |
| **Total** | **149,340** | **151,632** | **+2,292** | = 2,083 + 209 |

No file under `backend/app/web` or `content/` changed between `dda0af9` and HEAD (`git diff --stat` empty), so HEAD
in LF form equals the `dda0af9` row.

### Does the script count CRLF or LF; working tree or what is served?

It counts **whatever bytes the app serves from files on disk**: it uses an in-process client (`http://testserver`),
so static files are the raw working-tree bytes (CRLF counted when the file is CRLF), `sw.js` is the exception (read as
text, so LF). The git index is LF for all of these (`i/lf ... attr/text eol=lf`), but in this Windows tree `chat.js`,
`recorder.js`, `sw.js` are `w/crlf` (`core.autocrlf=true`), while `app.css` is `w/lf`. A fresh checkout (worktree, or a
Linux clone as Render does, **(assumed: deploy builds from a git clone; Dockerfile has `COPY . .`)**) gives LF.

### Step 3's 153,231 B (369 B headroom)

`git show dda0af9:eval/lowband/REPORT.md` says "149.64 KB raw" (KiB): 149.64 x 1024 = 153,231 B, timestamp
10:36:58 UTC (16:06:58 IST), one minute before the commit. **I cannot reproduce it.** Partial explanation: Step 3
then stripped 1,351 B of comments from `recorder.js` + `sw.js` (recorder 6,531 -> 5,918; sw 4,950 -> 4,212 in git),
which leaves 153,231 - 1,351 = 151,880 vs today's 151,632 (248 B unexplained). Ordering (report generated before the
comment strip) is **assumed**.

### What the running app serves (two uvicorn instances, throwaway DB `abhyas_measure`, mock providers, logged in as `teacher.demo2`, start screen skipped; DB dropped afterwards)

| | main tree (CRLF) | dda0af9 worktree (LF) |
|---|---|---|
| `/teacher` HTML | 26,528 | 26,528 |
| app.css | 35,484 | 35,484 |
| chat.js | 67,763 | 65,680 |
| recorder.js | 6,127 | 5,918 |
| ack.js / manifest | 1,097 / 514 | 1,097 / 514 |
| sw.js / offline.html / login | 4,207 / 9,854 / 5,979 | same |
| teacher bundle (html+css+chat+recorder+manifest) | 136,416 | 134,124 |
| + ack.js (what the page references) | 137,513 | 135,221 |

- The script's static numbers **match the server exactly** (same bytes per file). The CRLF/LF difference is real in
  what is served.
- **The script's `/teacher` is 20,607 B but a seeded demo2 page is 26,528 B (+5,921 B)**: the page contains the chat
  history, so it grows with the conversation. The script says so itself ("lower bound"). With a seeded page the
  script's "all assets" sum would be ~155 KB (LF) / ~157.6 KB (CRLF), i.e. above 153,600 B; but that sum also
  includes `/login`, `sw.js` and `offline.html`, which are not loaded together with the chat page.
- The app sends **no** `Content-Encoding` (checked with `Accept-Encoding: gzip`); gzip sizes in the script are computed
  locally. Whether the host compresses is **not verified** (hosted site not called).

### Which number to plan against

For what judges download on a Linux deploy, plan against the **LF figures**: chat first load =
HTML + 35,484 + 65,680 + 5,918 + 1,097 + 514 = **129,300 B (empty page) to 135,221 B (seeded demo2 page)**, i.e.
18.4 to 24.3 KB under 153,600 B. The scripted gate (**149,340 B, headroom 4,260 B**) is the strictest scripted number
and uses the empty page; the 151,632 B (1,968 B) figure only exists because of this machine's CRLF. If you
keep checking with the script on this machine, remember it overstates by 2,292 B. The 300 B stop rule would not have
triggered on any of these.

## Task 3: full suite (one run each, totals line kept)

- `python -m pytest -o addopts="-q --strict-markers" -rfE` at `f5667cb`, Postgres reachable, `TEST_DATABASE_URL`
  unset: `1566 passed, 129 skipped in 179.59s (0:02:59)`. Failures: none. Errors: none.
- `node --test backend/tests/js/chat.test.mjs`: `tests 65, pass 65, fail 0, cancelled 0, skipped 0`.
- The 129 skips are mostly Postgres-gated tests (`TEST_DATABASE_URL`) and the evaluator audio samples; I did not
  re-list them. (Separately, Postgres-gated reset + scene tests: 17 passed, 1 skipped in Task 1.)
- ruff and mypy were run on touched files (pass). Whole-repo `ruff check .` / `mypy --strict backend/app` were last
  run at the previous report and not repeated after `e004030`/`f5667cb` **(assumed still clean)**.

## Task 4: LIT_MATRA_BLENDING through SceneRunner (mocks forced, in-memory store, script from `stash@{0}^3`)

### HEAD (`f5667cb`, fixed tagger)

```
Initial: item मेला | ravi AKSHAR_BY_AKSHAR 0 | priya FIRST_AKSHAR_GUESS 0 | aman MATRA_DROP 0
T1 Teacher: प्रिया, बोर्ड पर क्या लिखा है? पढ़ो।          acts [repeat_question] -> priya  item मेला
   priya: मछली!                                            states ravi 0 / priya 0 / aman 0
T2 Teacher: प्रिया, म पर ए की मात्रा 'मे' और ल पर आ की मात्रा 'ला', मिलाकर पढ़ो।  acts [phonics_sound_out] -> priya  item मेला
   priya: हम्म… मे - ला। मेला!                             states ravi 0 / priya 2 / aman 0
T3 Teacher: प्रिया, बहुत बढ़िया! अब पूरा शब्द मिलाकर फिर से पढ़ो।  acts [praise_generic] -> priya  item मेला
   priya: हम्म… मे - ला। मेला!   aman: दीदी, आज मिड-डे मील में क्या है?   states 0 / 2 / 0
T4 Teacher: शाबाश! अब अगला शब्द पढ़ो: मछली             acts [praise_generic] -> none  item मेला
   ravi: मे - ला!                                          states 0 / 2 / 0
T5 Teacher: बस, आज का अभ्यास यहीं समाप्त करते हैं।        acts [stop]                  item मेला   states 0 / 2 / 0
```

### Pre-fix tagger (`dda0af9` worktree; `act_tagger.py` identical to `7f699b4`'s, `git diff --quiet` verified)

```
T1 same as above (priya: मछली!)                            states 0 / 0 / 0
T2 acts [phonics_sound_out, give_new_problem]  item -> मिलाकर
   priya: हम्म… मि - ला - क - र। मिलाकर!                   states 0 / 2 / 0
T3 acts [praise_generic, give_new_problem]  item मिलाकर
   priya: हम्म… मि - ला - क - र। मिलाकर!   aman: दीदी, आज मिड-डे मील में क्या है?   states 0 / 2 / 0
T4 acts [praise_generic, give_new_problem]  item -> पढ़ो
   ravi: प - ढ़ो!                                           states 0 / 2 / 0
T5 acts [stop]  item पढ़ो                                   states 0 / 2 / 0
```

### Why Turns 1-3 shifted by one versus the earlier verified run

Reconstruction (my reading of the earlier run: ravi first, then priya twice; **the original script is not available**):

```
turns: "रवि, बोर्ड पर क्या लिखा है? पढ़ो।" / "प्रिया, बोर्ड पर क्या लिखा है? पढ़ो।" /
       "प्रिया, म पर ए की मात्रा 'मे' ... मिलाकर पढ़ो।" / "प्रिया, बहुत बढ़िया! ... फिर से पढ़ो।"
HEAD:    T1 ravi: मे - ला!  (0/0/0) | T2 priya: मछली! (0/0/0) | T3 priya: हम्म… मे - ला। मेला! + aman mid-day-meal (0/2/0) | T4 praise_generic, item मेला
dda0af9: T1 ravi: मे - ला!  (0/0/0) | T2 priya: मछली! (0/0/0) | T3 acts [phonics_sound_out, give_new_problem], item मिलाकर, priya: मि - ला - क - र। मिलाकर! (0/2/0) | T4 give_new_problem, item मिलाकर
```

- It reproduces the earlier pattern exactly (ravi "मे - ला", priya "मछली", priya to PARTIAL on the third turn),
  identically on the fixed and the unfixed tagger for Turns 1-2. So the **shift is a script difference**: the stash
  script's Turn 1 addresses priya, the earlier run's first turn addressed ravi (inferred, not seen).
- **Not the tagger fix**: Turn 1-2 child lines and states are identical pre/post fix.
- **Not the engine**: between `7f699b4` and HEAD the only change under rule_engine/rehearsal/content moves/personas is
  `rehearsal/header.py` (scene header payload); `scene_runner.py` and `rule_engine/` are unchanged.
- What the tagger fix does change: the active word and the child's line at the turn where the teacher says
  "...मिलाकर पढ़ो" (pre-fix: item becomes मिलाकर and priya says "मि - ला - क - र"; the earlier verified run's
  "PARTIAL" turn would have carried that wrong word **(assumed)**).

### Recommended 60-second recording for `teacher.demo3`

Facts (verified by driving the real chat API on a throwaway DB, mock providers): demo3 starts on the **LEARN** step of
`LIT_MATRA_BLENDING` ("चरण 1 / 7: सीखना"), seeded buttons `btn_understood`, `btn_replay`, no scene. **It takes 3
teacher actions to reach the group scene**: (1) tap `btn_understood`; (2) send one sentence; (3) tap `btn_listen`.
After (3) the model-practice bubble and the scene intro appear and the scene header shows "आपकी बारी 0/8", board मेला.
There is no separate "group" button press needed in this flow.

| # | Teacher does | What appears |
|---|---|---|
| 1 | tap "समझ गई, आगे" (`btn_understood`) | coach: "अब 1 मिनट में अपने शब्दों में बताइए: इस तरीके में सबसे ज़रूरी क्या है? ..." with a skip button |
| 2 | say/type: `बच्चे मात्रा छोड़ देते हैं, इसलिए मैं अक्षर की ध्वनि मिलाकर पढ़ना सिखाऊँगी।` | coach: "धन्यवाद! आपने 2 में से 4 मुख्य बातें कहीं।" then the "सुनना चाहेंगी...?" prompt with `btn_listen` (see issue 1) |
| 3 | tap `btn_listen` | "आदर्श अभ्यास:" model bubble, then the scene intro "कक्षा 1। बोर्ड पर शब्द लिखा है: मेला। ..." (scene 0/8) |
| 4 | say: `रवि, बोर्ड पर क्या लिखा है? पढ़ो।` | ravi: **"दीदी, मे - ला!"** (real Claude voicing; mock voicing gave "मे - ला!") |
| 5 | say: `प्रिया, बोर्ड पर क्या लिखा है? पढ़ो।` | priya: **"मैडम… शायद… मछली।"** (mock: "मछली!") |
| 6 | say: `प्रिया, म पर ए की मात्रा 'मे' और ल पर आ की मात्रा 'ला', मिलाकर पढ़ो।` | priya: **"मैडम… मे… ला… शायद… मेला।"**, aman: **"दीदी, मेरा जवाब... शायद... मछली।"** (mock: aman asks about mid-day meal); priya's state goes 0 -> 2 (PARTIAL) |
| 7 | say: `बस` | feedback screen (see issue 2) |

- Steps 4-6 child wording above is from **one real-Claude run** (engine states are deterministic and equal to the mock
  runs; wording is voiced by the model and can differ per run, and Turn 4's tagged acts were
  `[praise_generic, repeat_question]` in the real run vs `[praise_generic]` in the mock run). Steps 1-3 and 7 below are
  **mock** output (no real-Claude run of the full SessionService flow was done).
- Timing: mock pipeline took 0.4-0.9 s per turn. **Real voice round-trip latency was not measured here**, so I cannot
  confirm 60 s. Seven teacher actions will not fit in 60 s live if each takes several seconds; cut steps 1-3 (do them
  off camera, or edit) and record steps 4-7 (about 4 spoken lines).
- Issue 1 (verified in the templates): `explain_back_reply` is `"{covered} में से {total}"` while English is
  `"{n_covered} of {n_total}"`. The Hindi order reads backwards ("2 में से 4"; it should be "4 में से 2"). Do not
  record step 2's reply until fixed or re-checked.
- Issue 2: in the mock run the feedback text said "आपने ठोस चीज़ (बंडल और तीलियाँ) इस्तेमाल की ..." and "अमन की गलती से
  जुड़ी है" for a literacy scene where no bundles were mentioned. I did not trace why; real-Claude feedback was **not run**.
  Do not script step 7 until it is checked with a real key.
- Aman's real-Claude line repeats priya's wrong guess "मछली" (his seeded bug is MATRA_DROP); not investigated.

## Task 5: Chip C and the tray (local; the live site was not called)

### Chip C: `सवाल: उल्टी गिनती करके घटाव कैसे सिखाएँ?` (text decoded from chat.js equals this string, NFC)

| Stage | Output |
|---|---|
| `match_intent(text)` | `ask` |
| `extract_ask_query` | `उल्टी गिनती करके घटाव कैसे सिखाएँ?` |
| `match_handbook_question` | **`None`**: not a curated handbook chip, so there is no stored-text fallback (`fallback_reply` not applicable) and it goes through the LLM classifier |
| retriever mode | BM25 only (`VOYAGE_API_KEY` empty; dense off). Gates: MIN_SCORE 0.1, MIN_MATCHED_TERMS 2, TOP_K 5 |
| `retrieve_supported(raw query)` | 5 chunks; **top `up_ganit_sandarshika_c1:p046:070`, score 0.4936**, matched_terms 3 (then p035:047 0.4672, p060:096 0.4438, ...). Its summary: counting backwards ("उल्टी गिनती") to find an earlier age, topical. |
| real `classify_question` (Claude) | `category=pedagogy`, `needs_clarification=False`, `confidence=0.9`, `search_query_hi="उल्टी गिनती घटाव सिखाना कक्षा 1-3"`, no fallback used |
| retrieval with that rewritten query | p035:047 0.5817, p045:069 0.545, p046:070 0.5301, p046:071 0.5297, p060:096 0.5236 |
| real `answer_guide_question` (Claude) | not escalated, `confidence=0.92`, `source_ids=[p046:070, p046:071]`; answer in Hindi about counting back 5-3, dots, number strip |
| **citation chip** | **Yes: 1 chip (`up_ganit_sandarshika_c1:p046:070`)** via `citations_for_chunks` |

Caveats: one run each for classifier and answerer (the answerer log says forced tool_choice is rejected by
`claude-sonnet-5-5` so it retried with `auto`); LLM output varies. Citation rendering in the browser was not checked;
this is the data the UI would receive.

### A1 / A2 / B through the Claude tagger (`tag_act`, scene = NUM_SUB_REGROUP_BUNDLES, item 43-27, children ravi/priya/aman). `ANTHROPIC_API_KEY` **is set** (length not shown; Bash and PowerShell both see it), `LLM_PROVIDER=anthropic`. 3 runs each, no guard or fallback log lines on any run.

| Chip (text sent) | Runs 1-3 |
|---|---|
| A1 `रवि, सही उत्तर 16 है` | all: `acts=[tell_answer]`, `addressed=ravi`, `problem=None`, quote `सही उत्तर 16 है` (run 3: `रवि, सही उत्तर 16 है`) |
| A2 `अब 61 में से 28 घटाओ` | all: `acts=[give_new_problem]`, `addressed=None`, `problem=sub 61-28`, quote = whole line |
| B `चलो 43 में से 27 फिर से करते हैं: देखो, 4 बंडल और 3 खुली तीलियाँ हैं, 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो।` | all: `acts=[concrete_representation, model_step_aloud]`, `addressed=all`, `problem=None`, quote `देखो, 4 बंडल ... खोलो` |

A1 is the tell-answer relapse trigger; A2 changes the scene's active problem to 61-28 (not a no-op).

### Tray (from the previous run)

The previous report's finding stands (open tray does not cover the input box at 360x640; not re-measured here).

## Verified by output vs assumed

Verified by output this session: all diffs and test results quoted; the three-state consent-test matrix; the
17-passed Postgres-gated run; the pinning test failing with the fallback; both payload measurements; the per-file CRLF
facts; the running-server measurements; the full suite and JS totals; both literacy transcripts and both reconstruction
transcripts; the demo3 API walk (mock); Chip C pipeline outputs and 9 tagger runs; real-Claude scene lines (one run).

Assumed / not verified: that a real demo reset resurrects a scene end to end; multi-worker behaviour; that Render
builds from LF git content and compresses text; the cause of the 7f699b4 failure being identical to HEAD-minus-fallback;
the ordering explanation of 153,231 B and the 248 B residue; real-Claude wording stability; real voice latency;
real-Claude feedback text; whole-repo ruff/mypy after the last commits.

## Side effects

- `.git/info/exclude` got a `.wt/` line. Two worktrees remain, **not removed** (deleting is on your forbidden list):
  `.wt/pre3` (`7f699b4`) and `.wt/s3` (`dda0af9`). `git worktree remove` them when you like; they are untracked and
  ignored. Note my shell was switched into `.wt/s3` by the harness twice; all commands used explicit paths.
- Scratch DB `abhyas_measure` created twice on the local `abhyas-db-1` container and dropped (verified count 0). Two local
  uvicorn servers (8011/8012) and one (8013) were started and killed by port. The dev DB `abhyas` was not written
  intentionally, but with the default `DATABASE_URL` the real-Claude runs logged to its `llm_call` table (queries seen in
  output; inserted rows **assumed**).
- Real Anthropic API calls: Chip C classifier + answerer (>= 2), 9 tagger calls, the 4-turn scene run (tagger + child
  voice per turn). Exact count and cost not measured.
- `check_first_load.py` regenerates the tracked `eval/lowband/REPORT.md` on every run; the tree shows it modified by
  line endings only (`git diff --ignore-space-at-eol` is empty). I did not commit it.
- The stash `stash@{0}` and branches `backup-*` were read only; nothing applied or dropped.

## Left undone

- Real-Claude run of the full demo3 flow (steps 1-3 and 7) and measured real latency for the recording.
- Fixing `explain_back_reply` word order and the literacy-scene feedback wording (reported, not changed).
- Whether other unit tests are sensitive to a reachable local Postgres.
- Hosted (LF, compressed) payload measurement; the app itself does not gzip.
- Posing "मछली" from "पढ़ो: मछली" (still not done).
