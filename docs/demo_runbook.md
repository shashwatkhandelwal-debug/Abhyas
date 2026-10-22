# Demo runbook

Exact click path for the video and the live demo. Passwords are in the submission form only.

## Before recording or presenting
1. `GET <host>/healthz` returns `status: ok` and the expected `git_sha`.
2. Run `python scripts/smoke_test.py --base-url <host>`; all steps pass.
3. Reset demo data: log out of `teacher.demo1/2/3` (logout resets each demo teacher to its seeded state), or press *Reset demo* on the admin page. The Render free plan has no shell; to reseed everything set `SEED_ON_BOOT=true` for one deploy (`docs/DEPLOY.md` §5).
4. Use a clean browser profile or a private window, 1280×720, Hindi UI text visible.
5. Real API keys set on the service; confirm the latency report header does not say "mock".

## Path 1: teacher rehearsal (about 90 s)
1. Log in as `teacher.demo2`. The chat opens in the rehearsal state.
2. Tap sample chip 1 ("रवि, तुमने 43 में से 27 कैसे घटाया?"). Ravi explains his bug and says 24, never 16.
3. Tap chip 2 (bundles). Children move to partial understanding.
4. Tap chip 3 (Hinglish tell-answer). Aman parrots the answer.
5. Finish the scene; the feedback card shows strength, change, exact words with a highlighted quote. Tap retry.

## Path 2: explain back and ask (about 40 s)
1. As `teacher.demo1` or `teacher.demo2`, tap sample chip 4 in the explain-back step; show the fidelity reply naming the missing point.
2. Tap chip 5; show the cited answer or the escalation.

## Path 3: ARP and trainer (about 40 s)
1. Log in as `arp.demo`: weekly digest lists consenting teachers only; the escalated question from chip 5 appears.
2. Log in as `trainer.demo`: module × batch view; batch KNP-B3 is suppressed (n < 10).
TODO(human): these pages depend on T32–T33; remove this path if they are not shipped by the freeze.

## Path 4: low-connectivity (about 20 s)
1. In the browser dev tools set the network to Offline.
2. Show the cached learn summary and last messages; send a text and show it queued in the outbox.
3. Go back online; the message sends automatically.
4. Toggle lite mode in the menu; audio plays only on tap.

## If something fails live
- Mock banner or odd English replies: provider keys missing; switch to the recorded fallback walkthrough.
- 429 "Too many messages": wait one minute (20 sends per minute per user).
- Stuck reply: refresh; the poll resumes from the last message.
