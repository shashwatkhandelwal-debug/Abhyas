# FIX2 report (branch fix/address-and-voice, from 50ae59a)

Status: F3 DONE, F1 DONE, F4 DONE, F2 DONE, F5 DONE. Nothing BLOCKED. Not merged, not deployed. Details in FIX2_LOG.md.

## F3 name step
Yes/no and filler words are rejected; a leading filler is dropped before the frame match. Outputs (typed and service path):
- "हाँ।" -> asks again (ask_name_again), nothing stored
- "जी" -> asks again; "yes" -> asks again; "ok" -> asks again
- "हाँ, मेरा नाम रिया है" -> रिया
- "मेरा नाम रिया है।" -> रिया
- "Riya" -> Riya
Voice goes through the same extract_name on the transcript, so "हाँ।" from STT is handled the same way.

## F1 address (mock child lines, same model reply "दीदी, सर, तो 7 में से 2 घटाया, 5 आया। उत्तर 45 है!")
- she (f): दीदी, तो 7 में से 2 घटाया, 5 आया। उत्तर 45 है!
- he (m): सर, तो 7 में से 2 घटाया, 5 आया। उत्तर 45 है!
- unset: तो 7 में से 2 घटाया, 5 आया। उत्तर 45 है!
- onboarding scene, "दीदी, सुनो! ..." -> f: दीदी, सुनो! ... / m: सर, सुनो! ... / unset: सुनो! ...
Root cause of "दीदी, सर": persona ravi.yaml speech_style said 'दीदी' कहकर बात करता है while the prompt said सर. Fixed in persona data (content and content-seed), prompt rule (address_rule) and a final fix_address on every outgoing child line (model and template paths). Catalog has no combined keys. Demo accounts: seed sets f; DB only allows f/m, so "unset" is function-level only.

## F4 no repeats
Template path, Ravi explain_bug, three consecutive same-state lines: "7 में से 2 गया 5। 45!" | "देखो, 7 में से 2 गया 5। 45!" | "7 में से 2 गया 5। 45!" (consecutive lines always differ; ANSWER: "45!" | "मेरा तो 45 आया!" | "45!").
Model path: the prompt holds the previous line and "Do not repeat it ... same mistake"; an identical model line counts as a failed attempt (retry once, then template). Teacher's words are given to the model so it can react to a spoken method.

## F5 onboarding feedback (move title shown as TITLE)
- asked + words: आपने रवि से पूछा कि 45 कैसे आया, अच्छा। आपने तरीका शब्दों में समझाया, पर रवि अभी भी वही गलती कर रहा है। इसलिए हम 'TITLE' से शुरू करेंगे।
- asked + objects: ...आपने बंडल और तीलियों से करके दिखाया, यह बच्चों को सबसे आसानी से समझ आता है। इसलिए हम 'TITLE' से शुरू करेंगे, ताकि यह तरीका और पक्का हो।
- told: आपने रवि को सही उत्तर बता दिया, पर उसने खुद सोचकर नहीं निकाला। इसलिए हम 'TITLE' से शुरू करेंगे, जहाँ बच्चे को खुद सोचने का मौका मिलता है।
- English told: You told Ravi the right answer, but he did not work it out himself. So we will start with 'TITLE', where the child gets the chance to think for himself.
All 16 act combinations are tested.

## F2 own voice note
Play control (local object URL, memory only) on the outgoing bubble at once, kept after the transcript; revoked on pagehide and logout; works offline and after a rejected send. No new upload or storage.

## Payload (check_first_load.py)
Before: first-load 130210 B, all assets 151331 B, headroom 2269 B.
After: first-load 130791 B, all assets 151912 B, headroom 1688 B (real about 1188 B, above the 1000 B floor).

## Verified (ran, this branch)
- ruff clean; mypy --strict backend/app scripts/keep_alive.py clean (197 files)
- Full gate via scripts/pytest_fresh_db.py: 2626 passed, 2 skipped (log %TEMP%\fix2_full_gate.log), includes the no-dash test and catalog twin tests
- node chat tests: 93 passed
- phone_layout_check: 0 of 144 failing; composer_layout_check: 0 failures; dashboard_layout_check: all PASS
- freeze_check --skip-gates --any-branch: secrets and placeholders PASS; "git tree clean" failed only because check_first_load regenerates eval/lowband/REPORT.md (committed with this report). Gates inside freeze_check were skipped (I ran them separately above); branch and /healthz not checked.
Note: another session started its own pytest_fresh_db run while mine was going (separate fresh DBs). Before that I waited for its earlier pytest to finish. test_state_machine happy-path fails when run alone against the local DB (also on the untouched base 50ae59a); it passed in the fresh-DB gate.

## Assumed (not run)
- Real Claude behaviour: only mocks were used. The new prompt wording (address rule, previous line, "react to what the teacher said") has not been tried with the live model.
- Real STT output, real phone playback of the local recording (object URL on Android Chrome), TTS of the new template variants (not prewarmed beyond what prewarm_lines generates).
- content-seed/messages_hi.yaml was not given the F5 keys (not loaded at runtime).

## Human checks on a real phone
1. Onboard as "Teacher (he)" by voice: Ravi should say सर or nothing, never "दीदी, सर".
2. At the name step say "हाँ": it must ask again; then say "मेरा नाम ... है" and see only the name stored.
3. In the Ravi scene explain borrowing in words twice: Ravi's second line must differ and react to what you said, keeping his mistake.
4. After the scene read the coach line: it must name what you did and why the first move.
5. Record a voice note: play control appears at once and still plays after the transcript; switch to airplane mode and record again; log out and check nothing was uploaded.
