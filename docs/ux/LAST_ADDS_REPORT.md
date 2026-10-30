# Last adds report

Built on `feat/last-adds` (from `50ae59a`), merged to main in `cf2bc20`. Details of decisions are in `docs/ux/LAST_ADDS_LOG.md`.

| Task | Status | What |
|---|---|---|
| L1 "मेरी प्रगति" / My progress | DONE | `class_profile/my_progress.py`, one deterministic message (last up to 5 practices, trend of earliest vs latest practice of the same move on four facts, one strength, one next step, a next-step button), third button at the end of practice feedback, typed words work on the LEARN, MODEL, FEEDBACK and DONE screens only, never inside a scene |
| L2 What worked for other teachers | DONE | `class_profile/peer_worked.py`, one line after "still stuck" and after the reason for "could not try", and on the check-in tip screen; cluster if 10 or more teachers, else all if 10 or more, else no line |
| L3 Docs | DONE | `docs/EVALUATOR_GUIDE.md` (exact taps per account), `docs/ux/PHONE_TEST_CHECKLIST.md` section L |

Both flags are off by default and on in demo mode: `MY_PROGRESS_ENABLED`, `PEER_WORKED_ENABLED`.

## Mock transcripts (seeded scratch database, real service, Hindi)

demo2, tap "मेरी प्रगति" on the done screen:

```
आपकी प्रगति, पिछले 5 अभ्यास:
1. हासिल वाला घटाव: बंडल खोलकर (20/10)
2. हासिल वाला घटाव: बंडल खोलकर (23/10)
3. हासिल वाला घटाव: बंडल खोलकर (26/10)
4. हासिल वाला घटाव: बंडल खोलकर (28/10)
5. हासिल वाला घटाव: बंडल खोलकर (29/10)
तुलना, हासिल वाला घटाव: बंडल खोलकर: पहला अभ्यास और सबसे नया अभ्यास
बच्चे से कैसे या क्यों पूछना: पहले नहीं, अब हाँ।
जवाब खुद बता देना: पहले हाँ, अब नहीं।
तीलियाँ या गुच्छे जैसी चीज़ें इस्तेमाल करना: पहले नहीं, अब हाँ।
बच्चे को नाम से बुलाना: पहले नहीं, अब नहीं।
एक ताकत: आप बच्चे से पूछती हैं कि उसने कैसे या क्यों किया।
अगला कदम: एक बच्चे को नाम से बुलाकर पूछिए।
   [अगला तरीका] [अभ्यास करें] [कक्षा के बाद: कैसा?]
```

demo2, follow-up, tap "अब भी अटके हैं" (peer line, then the way back to the scene):

```
'हासिल वाला घटाव': दर्ज कर लिया। इस पर एक दूसरे स्रोत में भी बात है। स्रोत पर टैप करके पूरा अंश पढ़ें:
स्रोत: निष्ठा FLN, पृष्ठ 427 (राष्ट्रीय)
इस दिक्कत में 11 शिक्षकों ने बताया कि 'हासिल वाला घटाव: बंडल खोलकर' वाला तरीका काम किया।
अब वापस रवि के पास: बोर्ड पर 43 − 27 है। रवि से पूछिए कि उसने यह कैसे किया।
   [वापस अभ्यास पर]
```

The same screens in English were captured too (counts and structure identical). The 11 is the demo cohort (the demo cluster has 7 consenting teachers, so the scope falls back to all demo teachers).

## Seed changes

- New `db/demo_history.py`, called from `db/demo_loop.py`: demo2 four and demo3 three ended demo rehearsals (scene, her tagged turns, score row, ids outside the cohort prefixes, so each demo login reset removes anything a session adds and restores these rows).
- Cohort top-up: "worked" follow-up answers on regrouping from enough consenting cohort teachers to reach 11, dated 36 to 46 days back so the 30-day trainer cards did not move (checked: worked 5, still stuck 7, could not try 2).
- `test_seed_postgres.py` expected check-in count raised by 6.

## Verified and assumed

Verified (run on the merged main, `cf2bc20`): full gate `2714 passed, 2 skipped`; ruff and mypy --strict were clean on the branch before the merge; node 93 of 93; phone layout 0 of 144; composer 0; dashboard layout 0 FAIL; no-dash and freeze-check tests; payload unchanged by this build (first load 130791 B, headroom 1688 B). Privacy: unit tests that nothing outside the chat service imports the progress module or reads the history, and a Postgres test that the ARP digest, trainer report, cluster pack and reported-vs-observed builders carry none of the demo practice text. Peer counts, scope fallback, n below 10, consent, 60-day window, demo kept apart from real, flag off, Hindi and English, WhatsApp button caps: unit tests.

Assumed (not run): behaviour on a real Android phone (three buttons on the feedback screen at 360 px, voice entry of "मेरी प्रगति"); the demo1 path in the guide (new teacher on the first learn screen); the hosted site, which has not been deployed or re-seeded with this code; the peer line on WhatsApp delivery (no WhatsApp code was touched).
