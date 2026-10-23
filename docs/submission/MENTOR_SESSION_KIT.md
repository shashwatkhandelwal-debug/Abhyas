# Mentor session kit (40 minutes)

**Purpose.** The rubric gives weight to proof that we tested with real users and changed the product because of
what they said. At the time of writing we have **no real user-testing results**: `eval/user_testing/sessions.csv`
has only its header row and both findings files are empty templates. This kit is how we get the first real
results from mentors, FLN coaches or teachers, and how we record what changed. Nothing here is a result.

Who can be a participant: a mentor, an FLN coach, a DIET or SCERT person, or a primary teacher. Say honestly in the
deck which one each person was. Mentors are not teachers; do not count their answers as teacher results.

## Before the session (10 minutes of your time, once)

1. Open the hosted app on a phone and on the laptop. Pick one free demo login (`teacher.demo1`, `teacher.demo2` or
   `teacher.demo3`); the password is `<DEMO_PASSWORD>`. Demo accounts are shared: chats reset on login and logout.
2. Have `docs/SAMPLE_INPUTS.md` open (copy-paste inputs) and the feedback form below printed or in a form tool.
3. Start a screen recording only if the participant agrees to the consent line below; otherwise just take notes.
4. Copy the change-log table (bottom of this file) into a shared sheet. One row per piece of feedback.

## Consent line (read it aloud, get a yes before starting)

**English:** "This is a prototype that lets a teacher practise a teaching move with a computer-simulated child. The
children are not real. We will note what you say and your ratings, without your name, to improve the product
and, if you agree, to show anonymised quotes and numbers in our hackathon presentation and video. You can stop at
any time, and you can say no to any part. Is that all right?"

**हिंदी:** "यह एक प्रोटोटाइप है जिसमें शिक्षक कंप्यूटर के बनाए एक बच्चे के साथ पढ़ाने का अभ्यास कर सकते हैं। बच्चे असली
नहीं हैं। आप जो कहेंगे और जो अंक देंगे, उन्हें हम बिना आपके नाम के नोट करेंगे, ताकि उत्पाद बेहतर हो सके, और आपकी सहमति
हो तो हमारी हैकथॉन प्रस्तुति और वीडियो में बिना नाम के उद्धरण और संख्याएँ दिखाई जा सकती हैं। आप कभी भी रुक सकते हैं और किसी
भी हिस्से के लिए मना कर सकते हैं। क्या यह ठीक है?"

Record the answer (yes / no / yes except video) in the first column of the change-log. If no, do not use their
words anywhere.

## Session script

| Min | What you do | What you say / ask | What to watch for |
|---|---|---|---|
| 0-3 | Welcome and consent | Read the consent line. Explain: "I am not testing you, I am testing the app. If you get stuck, that is the app's fault." | Their role and how often they work with teachers (write it down). |
| 3-6 | The problem | "Teachers are trained in teaching moves but rarely get to practise them. This app lets them practise by voice with a simulated child." | Do they recognise the problem? Any "that already exists" answers: ask what. |
| 6-9 | Login and first screen | Give them the phone. Say only: "Log in as `teacher.demo1` and tell me what you think you can do here." Do not explain the screen. | Where do they look first? Do they find the mic? Any hesitation at the demo banner or consent step. |
| 9-17 | One practice scene | Switch to `teacher.demo2`. Say: "Ravi has just said 43 minus 27 is 24. Say something to him by voice, in Hindi, the way you would in class." Let them talk for 3-4 turns. | Do they speak or type? Does Ravi's reply feel like a child? What do they do when he repeats a wrong answer? Do they tell him the answer (that is the relapse case)? |
| 17-21 | Feedback | Let them end the practice and read the coach's feedback. Ask: "In your own words, what did the coach say to do differently?" | Can they repeat it? Do they trust the quote of their own words? Is any Hindi unnatural? |
| 21-26 | The handbook | "Ask the handbook" chips: have them tap one and read the answer and the source. Then ask them to type or say one question of their own. | Is the cited page believable? Do they tap the citation? What did they ask that we could not answer? |
| 26-30 | My class and what to get better at | On `teacher.demo1`: menu > My class. Have them say where their class struggles and choose one thing they want to get better at. Then open Modules. | Does the chosen move come first? Do they understand why? Anything they wanted on the list but is missing (write it exactly). |
| 30-34 | Low connectivity | Put the phone in airplane mode, send a message, then turn it back on. | Do they understand the banner and the waiting clock? Do they trust that the message was not lost? |
| 34-40 | Feedback form and close | Hand over the form (below). Ask the two open questions aloud and write their words down. Thank them. Tell them you will report back what changed. | Exact quotes, in their language. |

**Rules for you.** Do not defend the product during the session. Do not explain a screen unless they are stuck for
more than 30 seconds, and write down every time you had to. If the app breaks, note the time and what they did.

## Feedback form (fill in on paper or a form tool)

Participant code (not a name): ______  Role: mentor / FLN coach / DIET-SCERT / teacher  Date: ______
Device and network: ______  Consent: yes / no / yes except video

1. **Did the simulated child feel like a real child in a classroom?** / **क्या नकली बच्चा कक्षा के असली बच्चे जैसा लगा?**
   1 (not at all) - 2 - 3 - 4 - 5 (exactly like them). What made it feel real or unreal? / क्या असली या नकली लगा?
2. **Would this help a teacher practise a move before using it in class?** / **क्या इससे कोई शिक्षक कक्षा में आज़माने से पहले अभ्यास कर पाएगा?**
   1 (no) - 2 - 3 - 4 - 5 (very much). Why? / क्यों?
3. **Was the coach's feedback clear and something you could act on tomorrow?** / **क्या कोच की प्रतिक्रिया साफ़ थी और कल से अमल में लाई जा सकती थी?**
   Yes / Partly / No. What would you change? / क्या बदलेंगे?
4. **Was the handbook answer and its source page believable?** / **क्या हैंडबुक का जवाब और उसका पन्ना भरोसे लायक था?**
   Yes / Partly / No. A question you wanted answered that it could not: / ऐसा सवाल जिसका जवाब नहीं मिला:
5. **Was anything confusing, slow or hard to do on a phone?** / **क्या कुछ उलझाने वाला, धीमा या फ़ोन पर मुश्किल था?**
   Where exactly? / कहाँ?
6. **Would you use something like this once a week for about 15 minutes?** / **क्या आप हफ़्ते में लगभग 15 मिनट ऐसा कुछ इस्तेमाल करेंगे?**
   Yes / Maybe / No. What would stop you? / क्या रोकेगा?
7. **What is the one thing you would change first?** / **सबसे पहले आप क्या बदलेंगे?**
8. **Anything wrong, unfair or misleading that a teacher could be misled by?** / **क्या कुछ ऐसा है जो गलत या भ्रामक हो सकता है?**

Optional: how many teachers do you work with, and what would they need to start? / आप कितने शिक्षकों के साथ काम करते हैं और उन्हें शुरू करने के लिए क्या चाहिए?

## After the session (the same day)

1. Add one row per session to `eval/user_testing/sessions.csv` (the file already has the columns; leave a column
   empty rather than guess; the CSV has no name column, keep it that way).
2. Write each piece of feedback as a row in the change-log below, with a decision: **fix now**, **fix after
   freeze (roadmap)** or **won't fix, because ...**.
3. When a fix is committed, put the commit SHA in the row. Rows without a SHA are not "changed", they are
   "planned", and the deck must say so.
4. Re-run the relevant check after the fix (the test, or the page on a phone) and tick the last column.

## Change-log template (feedback -> change -> commit)

| # | Date | Who (role, code) | Consent | Feedback (their words, translated if needed) | Where in the app | Decision | Change made | Commit SHA | Verified how | Verified |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | | | | | | fix now / roadmap / won't fix | | | | [ ] |
| 2 | | | | | | | | | | [ ] |
| 3 | | | | | | | | | | [ ] |
| 4 | | | | | | | | | | [ ] |
| 5 | | | | | | | | | | [ ] |

**For the deck's "user inputs and testing" page** (one to two pages), report only what the table supports:
how many people, in which roles, what the average ratings were (say n for every number), the top five pieces of
feedback, and for each the change and its SHA. State plainly that the sessions were with mentors and coaches
where that is the case, and that no teacher classroom outcome has been measured.
