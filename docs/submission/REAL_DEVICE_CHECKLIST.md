# Real-device checklist (low-cost Android, 3G / 2G)

**Why:** the judges will test low connectivity, and everything we have measured so far was measured on a laptop
(`docs/PERFORMANCE.md`). Nothing in this file has been run yet: every Pass / Fail cell below is empty on purpose.
Fill it in on a real phone before the freeze and keep the filled copy (a photo of the table is enough) as
evidence for the "ability to work in real scenarios" section of the deck.

## Before you start

| Item | What to write down |
|---|---|
| Phone model and Android version | |
| Browser and version (Chrome recommended) | |
| RAM / free storage | |
| Network used (SIM operator, or a throttling profile) | |
| Hosted URL tested | `<HOSTED URL>` |
| Git SHA shown by `<HOSTED URL>/healthz` | |
| Date, tester | |

**How to get 3G / 2G on a normal phone.** Either (a) use the phone's own network setting to force 2G/3G on a SIM
in a weak-signal place, or (b) on a laptop with the phone connected over USB, open `chrome://inspect`, inspect the
phone's tab and use DevTools > Network > Throttling (Slow 3G; add a custom "2G" profile of 50 kbit/s down,
20 kbit/s up, 800 ms latency). Say which one you used in the table above. Use a stopwatch for every "time" cell.

**Demo accounts are shared.** Use `teacher.demo1`, `teacher.demo2` or `teacher.demo3` with `<DEMO_PASSWORD>`
(the login page shows which are free to take: pick one that nobody else is using; chats reset on login and logout).

## The checks

Pass means: it did what the "Expected" column says, without you doing anything extra. Write what you saw in Notes,
especially for a Fail.

| # | Check | How | Expected | Time (s) | Pass | Fail | Notes |
|---|---|---|---|---|---|---|---|
| 1 | Cold start, first ever load | Clear site data, open the hosted URL on 3G, start the stopwatch, stop when the login form is usable | Login page shows; if the server was asleep the page says it is waking up and opens by itself (up to about a minute) | | | | |
| 2 | Page weight | DevTools > Network, hard reload the chat page after login | First load is under 150 KB excluding audio (the budget `scripts/check_first_load.py` checks) | | | | |
| 3 | Login | Log in as `teacher.demo1` on 3G | Chat opens with the welcome messages | | | | |
| 4 | Install / add to home screen | Chrome menu > Add to Home screen, open from the icon | Opens full screen, same chat | | | | |
| 5 | Voice note, 3G | Hold the mic, say a Hindi sentence (sample inputs 1 or 2 in `docs/SAMPLE_INPUTS.md`), release | Status line goes recording > sending > understanding; your words appear; the child answers (text first, audio when ready) | | | | |
| 6 | Voice note, 2G | Same as 5 on the 2G profile | Either it completes or it says clearly what to do ("type instead"); never a blank or raw error | | | | |
| 7 | Typed message | Type sample input 2 and send | Reply arrives; the tick turns from clock to check | | | | |
| 8 | Handbook chip | Tap one of the four "Ask the handbook" chips | Answer cites a source and page; tapping the citation opens the excerpt | | | | |
| 9 | Offline send | Turn on airplane mode, type a message, send | Banner says you are offline; the message shows a clock and stays in the outbox | | | | |
| 10 | Offline reading | Still offline, scroll the chat, open the menu, open `/offline.html` pages | History stays readable; nothing crashes | | | | |
| 11 | Reconnect | Turn airplane mode off | Banner clears; the waiting message sends by itself; the reply arrives | | | | |
| 12 | Failed send | Send, then drop the connection for more than the retry window | A red **!** appears on the message; tapping it resends | | | | |
| 13 | Lite mode | Menu (the three dots) > lite mode on, then get a reply that has audio | Audio is not downloaded until you tap play; text still arrives | | | | |
| 14 | Lite mode survives reload | Reload the page | Lite mode is still on | | | | |
| 15 | Switch to English | Language switch on the login page or in the menu | Interface becomes English; the children and coach still speak Hindi | | | | |
| 16 | Low-memory behaviour | Open 5 other apps, then return to the browser tab | Page restores or reloads without losing the sent messages | | | | |
| 17 | Logout and reset | Log out, log in again | Chat is back at its starting state (the demo account was reset) | | | | |

## What to report back

1. Rows that failed, with what you saw and what you tried.
2. The slowest row in each of rows 1, 5 and 6 (seconds). Report them as "measured on `<phone>` on `<network>`
   on `<date>`" and nowhere else; do not generalise.
3. Anything on the phone that looked broken but is not in the table (text too small, buttons too close together,
   keyboard hiding the input).

Known limits to expect (not failures): the very first request to a sleeping free-tier server is answered by the
hosting service's own waiting page, before our page can load; voice depends on the speech provider keys being
configured on the deployment (with none, the mock audio is used and says so); the speech services need a network,
so on 2G a voice note can time out and ask you to type instead.
