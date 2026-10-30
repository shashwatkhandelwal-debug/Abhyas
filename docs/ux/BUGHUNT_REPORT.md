# Bug hunt report (fix/fix3)

Phase 1 (FIND) ran on the real app in Docker with the real model. No app code was changed in phase 1.
Status columns are filled in at the end of phase 3.

## What ran

| Journey | Ran | Notes |
|---|---|---|
| A onboarding (8 variants: male/female x Hindi/English UI, name answers, consent, ARP code, 8 reply types) | yes, phone | Two earlier batches were discarded: shared demo state leaked between runs and two batches overlapped. The final batch was clean and sequential. |
| B rehearsals | partly, phone | Regrouping with Ravi (10 turns), Priya, Aman, Ravi as a male-teacher account; NUM_COMPARE (Ravi); LIT_LETTER_SOUND group scene; LIT_MATRA group scene (5 turns). Shorter than the 10 turns asked: the live-call cap (400) did not allow 10 turns for every child on every scene. Priya and Aman were only run on regrouping. |
| C Guide | yes, phone | 5 Hindi (4 answered, 1 honest "not in the documents"), 1 English chip path not reachable after `/lang/en` redirect (see B21), 1 off-topic, 1 injection (declined). |
| D demo logins and reset | yes, phone | demo1/2/3, three follow-up buttons on demo2, daily tip on/off on demo3, reset x3 per account. |
| E teacher features | yes, phone | class check-in walked through every topic, level and struggle option (no errors), my class, delete my data (found P0), my progress, language switch from the menu. Observation/visit note to the teacher: ARP form not exercised (no teacher-side message produced in the run). |
| F ARP, trainer, coach, admin pages, CSVs | yes, phone and desktop | No overflow, no console error, no 5xx. CSV headers and PII checked. |
| G robustness | yes, phone | anonymous hits, offline then online, slow 3G, double tap, two tabs, back button. The 10-minute idle step was not run. |
| H static sweep | yes | Both catalogs scanned for em dashes, scripts, raw codes, gender forms. |

Desktop (1366x768): only journey F was run on desktop in phase 1. Voice was not tested (verified by hand).
Live LLM calls used in phase 1: about 265 of 400 (counted as `llm_role` log lines).

## Bugs

Severity: P0 breaks a flow or leaks/destroys data, P1 a judge would notice in 15 minutes, P2 polish.

| ID | Sev | Where | What the user sees | Expected | Root cause (file:line) | Fix plan |
|---|---|---|---|---|---|---|
| B02 | P0 | E, "delete my data" on teacher.demo1 | After "हाँ, मिटाएँ" the teacher and the login row are gone; the next login says "गलत यूज़रनेम या पासवर्ड" for every judge until a reseed | A shared demo account is reset, never deleted | `backend/app/web/teacher.py:890` calls `purge_teacher_data` for demo accounts | For shared demo teachers call the reset path (`reset_demo_teacher`) instead of purging; same confirmation page |
| B03 | P1 | G, anonymous GET /teacher, /arp, /trainer, /review, /admin | Raw JSON `{"detail":"Not authenticated"}` with HTTP 401 | A page request without a session goes to the login page | `backend/app/auth/guards.py:63` raises 401 for every route | For HTML navigation (Accept: text/html) answer with a redirect to `/login`; keep 401 JSON for API calls |
| B01 | P1 | A, address-form step | Typing "हाँ" (or anything but a button) picks the feminine form: "सुनील जी, आप कितने साल से पढ़ा रही हैं?", Ravi then says "दीदी" to a male teacher | Only the two buttons (or a clear male/female word) set the form; anything else re-asks | `backend/app/sessions/state_machine.py:1108-1112`, `else` branch defaults to "f" | Accept explicit tokens only, otherwise stay in the state and re-ask with the buttons |
| K1 | P1 | A and B, Ravi, Priya and Ravi (compare) | Ravi: "…तो 45!" then after the teacher tells the steps "…उत्तर 45!" (same line); in regrouping three identical lines; in compare an exact repeat; "आज बाहर बारिश हो रही है न?" gets the math line again | No near-repeat; if the teacher explained, the child reacts to it; off-topic gets a reaction | `backend/app/llm/roles/child_voice.py:~290` repeat check is exact equality only; no telling state | Normalised near-repeat check (>= 0.8), one retry then template; telling/explaining state with template lines; off-topic reaction |
| K2 | P1 | A, feedback after the 2 onboarding turns | Telling the procedure in turn 2 is not mentioned | A deterministic extra line | `backend/app/sessions/placement_feedback.py` only maps tagger acts; telling is untagged | Deterministic detector on later turns, extra catalog line (hi and en) |
| K3 | P1 | A, after feedback | The move name appears three times in a row ("So we will start with…", "Your first move is…", "This week's move…") | Name once, then the key points | `backend/app/sessions/service.py:2111-2133` sends feedback, `ready_first_move`, then `learn_intro` | Drop `ready_first_move` line when the feedback already names the move |
| K4 | P1 | A, Guide tip after onboarding; B, learn step official excerpt | "बच्चों के साथ घर पर गिनती की गतिविधियाँ करवाने के लिए अभिभावकों को…" for a bundles move; feminine verb for a male teacher; learn step on regrouping shows an excerpt about multiplication and division | On-topic tip, no home/parent passages, no feminine verb for male, none if nothing qualifies | `backend/app/sessions/service.py:576-655` (`_cited_tip`) takes whatever retrieval returns | Filter candidate chunks by move keywords, exclude home/parent passages, skip feminine reader verbs for male, no tip otherwise |
| K5 | P1 | D, all demo logins | Banner "डेमो: लॉगिन/लॉगआउट पर चैट रीसेट" says nothing about what the demo shows | One banner per demo account | `backend/app/web/teacher.py:95-99` one shared message | Per-account banner keys, hi and en |
| K6 | P1 | D, demo2 | Follow-up card ("कल आपने कक्षा के बाद बताया… काम किया / अब भी अटके हैं / आज़मा नहीं सके") appears between Ravi's seeded line and the rehearsal | Before the rehearsal block or after it ends | `backend/app/sessions/service.py:998-1020` offers on open; the seeded scene is not counted as `spoken` | Seed the card before the rehearsal messages (marked offered) |
| K7 | P1 | D, demo2/3 | Seeded bubbles "17:56", live ones "11:28 pm" (and the seeded time is UTC, 5.5 h behind) | One format everywhere | `backend/app/web/teacher.py:189-193` formats UTC 24-hour on the server; `chat.js:1182` formats live in the browser | Format every bubble in the browser from `data-created-at` |
| B07 | P1 | D, demo2 | Typing "मेरी प्रगति" inside the active scene is sent to Ravi as a teacher turn (the K5 banner asks the judge to open it) | The command opens my progress | scene turn capture runs before the my-progress intent | Recognise the exact command during a scene |
| B08 | P1 | D, demo3 "मेरी प्रगति" | "हासिल वाला घटाव: बंडल खोलकर (21/10)" reads as a score of 21 out of 10 | A date that reads as a date | `backend/app/class_profile/my_progress.py` formats dd/mm | Show "21 अक्टूबर" |
| B09 | P1 | E, delete page, male teacher | "क्या आप वाकई अपना सारा डेटा हटाना चाहती हैं?" | Masculine form ("चाहते हैं") | `delete.html` calls `get_message` without the teacher's address form (the catalog has `text_m`) | Pass the address form |
| B04 | P2 | A, name | Latin name in a Hindi sentence ("Riya जी"); "DEMO" accepted as a name | cosmetic | name step | left |
| B10 | P2 | Hindi UI | English glosses: "प्रगति (Progress)", "प्रमाण सीढ़ी (EVIDENCE LADDER)", "(RUBRIC SCORES)", "(KEY POINTS COVERED)"; ARP week "26 Oct 2026"; trainer "ज़िला: Kanpur Nagar" | Hindi only | catalog `ui_chat_menu_progress`, `ui_progress_*`; ARP date format; district name | remove glosses if time allows |
| B11 | P2 | trainer CSV | `export.csv` has English headers while the other CSVs have Hindi | one language | `backend/app/web/trainer.py` export | left |
| B12 | P2 | A, consent | Typed "Learn more" / "I agree" in the Hindi flow re-asks | accept | intents | left |
| B13 | P2 | LEARN step | A typed question without the "सवाल:" prefix gets "press the button" | by design (free text is the step's input; Guide is chips or the prefix) | n/a | left, documented |
| B14 | P2 | girl child grammar | "प्रिया ... सही करता है", "प्रिया असली कक्षा के बच्चे जैसा लगा?" | feminine for Priya | persona-neutral catalog strings | left |
| B15 | P2 | G, two tabs | A second tab did not show the first tab's new messages within 8 s | live update | polling | left |
| B16 | P2 | demo3 | Progress history is four regrouping attempts although three modules are "completed" | consistent story | demo seed | left |
| B17 | P2 | phone, 3-children scene | The suggestions sheet clips the "डेमो शॉर्टकट" block at the bottom | no clipping | sheet height | left |
| B18 | P2 | explain-back | "आपने 4 में से 0 मुख्य बातें कहीं" for a sensible literacy explanation | fairer scoring | fidelity checker output (model) | left |
| B19 | P2 | `/lang/hi` with no `next` while logged in | Goes to /login | stays on page | `ui_lang.py` default redirect | left |

Counts: P0 1, P1 14 (B01, B03, B07, B08, B09 and K1 to K7 counted as 7 → B01, B03, B07, B08, B09, K1, K2, K3, K4, K5, K6, K7), P2 11.
