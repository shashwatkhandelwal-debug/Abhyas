# Demo runbook

Exact click path for the video and the live demo. Passwords are in the submission form only.

## Before recording or presenting
1. `GET <host>/healthz` returns `status: ok` and the expected `git_sha`.
2. Run `python scripts/smoke_test.py --base-url <host>`; all steps pass.
3. Reset demo data: log out of `teacher.demo1/2/3` (logout resets each demo teacher to its seeded state), or press *Reset demo* on the admin page. The Render free plan has no shell; to reseed everything set `SEED_ON_BOOT=true` for one deploy (`docs/DEPLOY.md` §5).
4. Use a clean browser profile or a private window, 1280×720, Hindi UI text visible.
5. Real API keys set on the service; confirm the latency report header does not say "mock".

## Path 1: teacher rehearsal, one-on-one (about 2 min)
1. Log in as `teacher.demo2`. The chat opens **inside a 1-1 scene with Ravi** (header: "रवि से 1-1 बात", board 43 − 27, progress cue, turn 1/10, end button).
2. Type or speak "देखो, ये 4 बंडल और 3 खुली तीलियाँ हैं, 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो।": the cue moves to "आधा समझ आया" (Ravi reaches partial understanding, driven by the rule engine).
3. Tap the Hinglish tell-answer chip: Ravi repeats the answer without understanding and the cue does not move.
4. Type a new problem ("अब 61 में से 28 करो"): Ravi relapses to his bug (no free pass because he was told).
5. Finish with the **end practice** button; the feedback card shows strength (your own words quoted), one change, exact words, on the one-on-one rubric. Tap retry.
6. Retry shows the choice **1-1 बच्चे से बात / तीन बच्चों के साथ**. Pick 1-1, choose Priya, tap the diagnosis chip ("उलझन पहचानें"): the diagnosis verdict (wrong for Priya, because her mistake is a different one) is shown, then her real mistake is revealed and the scene starts.
7. Optional: type "रवि, 200 में से 120 घटाओ": the child says it is too big (out of range), no placeholder text.
8. Optional: the same retry choice with **तीन बच्चों के साथ** starts the old three-children scene.

## Path 2: explain back and ask (about 40 s)
1. As `teacher.demo1` or `teacher.demo2`, tap the explain-back chip in the explain-back step; show the fidelity reply naming the missing point.
2. Tap the multi-grade question chip; show the cited answer or the escalation.

## Path 3: ARP and trainer (about 40 s)
1. Log in as `arp.demo`: weekly digest lists consenting teachers only; the escalated question from the multi-grade question chip appears.
2. Log in as `trainer.demo`: module × batch view; batch KNP-B3 is suppressed (n < 10).
Both pages are shipped (see `docs/JUDGE_QUICKSTART.md` for what each role shows).

## Path 4: low-connectivity (about 20 s)
1. In the browser dev tools set the network to Offline.
2. Show the cached learn summary and last messages; send a text and show it queued in the outbox.
3. Go back online; the message sends automatically.
4. Toggle lite mode in the menu; audio plays only on tap.

## If something fails live
- Mock banner or odd English replies: provider keys missing; switch to the recorded fallback walkthrough.
- 429 "Too many messages": wait one minute (20 sends per minute per user).
- Stuck reply: refresh; the poll resumes from the last message.
