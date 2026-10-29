# Human checks (things no test or mock could verify)

Do these on the **hosted site** after a manual deploy of main, on a real Android phone in Chrome unless noted. Passwords are in the
submission form. Note failures with a screenshot and the time. Full phone walk-through: `docs/ux/PHONE_TEST_CHECKLIST.md`.

| # | Unverified item | What to type or tap | Good looks like |
|---|---|---|---|
| a | Real Claude tagger with male phrasing (tests use a scripted tagger) | Log in as `teacher.demo2`. In the scene with Ravi, say or type: **मैं करके दिखाता हूँ, देखो 52 में से 17 ऐसे घटाते हैं।** Then, in a fresh scene, **रवि, तुमने कैसे किया? मुझे एक-एक कदम बताओ।** | Ravi answers each line sensibly; the first line is read as showing/telling (the scene bar may move to "फिर अटका" only after a new problem), the second as asking him to explain. No error bubble, no feminine wording about you. Check `/admin` guard results for tagger failures. |
| b | Check-in tip read aloud in Hindi | In the chat tap **कक्षा के बाद: कैसा रहा?**, answer "कुछ बच्चों को मुश्किल", pick a difficulty, then tap the speaker on the tip. | Clear Hindi audio of the tip within a few seconds, same words as the text, ends with the handbook source line. |
| c | WhatsApp reply-button and list limits | Only with a real WhatsApp number linked (credentials needed): run the check-in and the "कक्षा को स्तर के हिसाब से समूहों में बाँटें" flow. | At most 3 reply buttons per message, each title at most 20 characters, nothing cut off; web may show up to 5. Mark "not tested" if no number exists. |
| d | In-scene check-in chip in a real phone browser | During a scene (`teacher.demo2`) look above the keyboard. | The check-in chip is visible with the input bar fully on screen; open the keyboard and the input and send button stay visible. |
| e | Told-answer strip beat | In a one-on-one scene say **उत्तर 16 होता है।** (he only repeats it), then **अब ये करो: 61 में से 28।** | Beside Ravi the label reads **अटका हुआ · फिर अटका** after the new problem (not before). A hard page reload may show plain "अटका हुआ" until the next message; that is known. |
| f | Cold start after 20 minutes idle | Leave the site untouched for 20+ minutes (UptimeRobot off), then open `/teacher`. | The page eventually loads (about a minute on the free plan) and the offline page or retry works; no half-broken login. |
| g | Five log-out / log-in cycles | `teacher.demo1`: log out, log in, repeat five times; each time say one line. | Every login starts from the starting state, no error, no stale messages from the previous cycle, input bar always visible. |
