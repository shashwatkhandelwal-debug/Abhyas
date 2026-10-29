# Demo script: 3 minutes

Every step below uses a flow that exists in this build and has a passing test. The expected text was produced
by running the real `SessionService` on the **mock path** (no language model, no network, `DEMO_MODE` on, address
form "she") with `scripts`-style harnesses; it is pasted as printed. Lines marked **[varies with live LLM]** are
phrased by a model on the hosted site (or by the keyword fallback when no key is set), so the wording will differ from
this page; the numbers and the logic do not. On the hosted site, log out between takes: the three teacher logins
reset on logout.

Accounts: `teacher.demo2` (check-in, practice, tray) for steps 2 to 4 and 5; `teacher.demo3` is the cleaner start for
the level sorter; `trainer.demo` for the cluster pack. Password: see the submission form.

## 0:00 to 0:20. Problem hook (voice-over, no screen)

Say: "In the CSBC and Ashoka trial with about 1,900 grade 3 teachers in Sitapur and Hardoi, neither a WhatsApp
chatbot nor micro-videos improved adoption, knowledge or valuation, and only 15 to 20 percent stayed consistently
active. Two-thirds of Class 1 and 2 classrooms are multigrade, per ASER school observations. Abhyas is built around
those two facts: short taps, official sources, and practice with a child who behaves the same way every time."
(Sources: idronline.org and countercurrents.org, quoted in `docs/submission/PITCH_NOTES.md`.)

## 0:20 to 0:55. After-class check-in (teacher.demo2, inside the scene)

Screen: log in as `teacher.demo2`; the chat opens inside the one-on-one scene with Ravi. Open the tray chip
**"कक्षा के बाद: कैसा रहा?"** and tap, in order: the chip, "हासिल वाला घटाव", "ज़्यादातर अटके", "हासिल वाला घटाव".
Say: "No typing, nothing about any child is saved, and the tip comes with its official source."

Expected (mock path, deterministic, **not** model text):

```
--- tap btn_chk_start
कक्षा के बाद की जाँच: आज बच्चों के साथ किस विषय पर काम हुआ? नीचे से चुनिए।
   buttons: [दहाई-इकाई, संख्या] | [हासिल वाला जोड़] | [हासिल वाला घटाव] | [मात्रा वाले शब्द] | [और विषय देखें]

--- tap btn_chk_mod_NUM_SUB_REGROUP_BUNDLES
'हासिल वाला घटाव' में बच्चों के साथ कैसा रहा?
   buttons: [अच्छा रहा] | [कुछ बच्चे अटके] | [ज़्यादातर अटके]

--- tap btn_chk_most
'हासिल वाला घटाव' में बच्चे कहाँ अटके? एक चुनिए।
   buttons: [हासिल वाला घटाव]

--- tap btn_chk_str_NUM_SUB_REGROUP
'हासिल वाला घटाव': पुस्तिका के आधार पर सुझाव:
घटाव में पहले "बचे कितने" वाले सवाल ठोस चीज़ों से हल करवाएँ और बच्चों को अपने तरीके बनाने दें; मानक तरीका उसके बाद सिखाएँ।
स्रोत: निपुण भारत दिशानिर्देश, पृष्ठ 281 (राष्ट्रीय)
स्रोत: निष्ठा FLN, पृष्ठ 427 (राष्ट्रीय)
दर्ज कर लिया गया। इसमें बच्चों की कोई जानकारी दर्ज नहीं होती।
इस दिक्कत के लिए अभ्यास का केस है: हासिल वाला घटाव: बंडल खोलकर। चल रहा अभ्यास वहीं रुका है। अभी उसी पर लौटिए, या हैंडबुक से पूछिए।
   buttons: [वापस अभ्यास पर] | [हैंडबुक से पूछें]

--- tap btn_chk_resume
अब वापस रवि के पास: अपनी अगली बात कहिए।
```

## 0:55 to 1:35. Hero beat: tell the answer, Ravi parrots, the old mistake returns

Screen: the scene bar shows Ravi's label, "अटका हुआ". **Type or speak these three lines; do not wait for the A1/A2/B
chips.** Those chips appear only after 30 seconds idle in a subtraction scene, so on camera they will not be there.
Say: "Ravi's answers come from a rule engine, not a model. I ask how. Then I just tell him the answer. He repeats it
without understanding. On a new problem the old mistake is back, and the label says stuck again."

Lines to say, in order: "तुमने यह कैसे किया?", then "सही उत्तर 16 है।", then "अब 61 में से 28 घटाओ।".

Expected (real `SessionService`, mock path, scripted act tagger; the strip text is `strip_label`). **[varies with live
LLM]**: on the hosted site the model or keyword fallback tags the lines, so check that "सही उत्तर ... है" is tagged as
telling the answer; the numbers and the logic do not change.

```
--- teacher asks how
3 में से 7 नहीं घटता। तो 7 में से 3 घटाया, 4 आया। 4 में से 2 घटाया, 2 आया। 24!
STRIP: अटका हुआ

--- teacher tells the answer
16… ?
STRIP: अटका हुआ

--- teacher gives a new problem
1 में से 8 नहीं घटता। तो 8 में से 1 घटाया, 7 आया। 6 में से 2 घटाया, 4 आया। 47!
STRIP: अटका हुआ · फिर अटका
```

Test: `backend/tests/unit/test_demo_hero_beat.py` runs exactly this beat. If you want the bundles version instead
(ask how, bundles and sticks, new problem), the coach line changes to the scaffold-relapse sentence below.

## 1:35 to 2:05. Feedback with the quote badge and the talk-move line

Screen: say "बस" to end. The coach bubble opens with one line naming what happened, then the teacher's own words in
the quote badge, then the talk-move lines. Say: "The advice quotes what the teacher actually said, and the last two
lines count what she did. Here it says she told the answer."

Expected (the coach lines are from the deterministic fallback; **[varies with live LLM]** for the coach's own
strength/change sentences, while the first line and the talk-move block are always built from tagged acts and the
engine's recorded answers):

```
चलिए, अब फीडबैक देखते हैं।
आपके अभ्यास पर सुझाव:
आपने रवि को उत्तर बता दिया, इसलिए उसने बिना समझे उसे दोहरा दिया। पहले उससे समझाने को कहकर देखें।

👍 आपने बच्चे से उसका तरीका पूछा, इससे उसकी असली उलझन सामने आई। आपके शब्द: «तुमने यह कैसे किया?»
🔁 उत्तर बताने के बजाय दो उत्तर सामने रखकर पूछिए कि कौन-सा सही है।
🗣️ अगली बार ऐसे कहकर देखें: "तुमने पहले एक उत्तर कहा था, अब तीलियाँ गिनकर दूसरा आया। कौन-सा ठीक है, और क्यों?"

💬 बच्चों से बात करने का तरीका
👍 आपने बच्चे से पूछा कि उसने यह कैसे किया। आपके शब्द: «तुमने यह कैसे किया?»
➡️ इस बार जवाब बता दिया गया। अगली बार पहले पूछें: 'तुमने यह कैसे किया?'
```

If the take uses bundles instead of telling the answer, the first line is: "नए सवाल पर रवि की पुरानी गलती फिर लौट आई।
उससे फिर चीज़ें हाथ में लेकर समझाने को कहें।" (it never claims the answer was told).

## 2:05 to 2:30. Level sorter (teacher.demo3)

Screen: tap the tray chip **"कक्षा को स्तर के हिसाब से समूहों में बाँटें"**, "पढ़ना", then the range for each of
the four levels: 6-10, 11-20, 1-5, 0. Say: "Rough counts, no names. Each group gets one 10-minute activity from the
UP handbook, with the page."

Note: the level sorter needs about six taps (chip, subject, four range answers). Record it in maths (fewer groups to
read out) or in one take; do not cut it mid-way.

Expected (deterministic):

```
--- sorter: tap chip
कक्षा को स्तर के हिसाब से समूहों में बाँटते हैं। किस विषय के लिए? नीचे से चुनिए।
   buttons: [पढ़ना] | [गणित]

--- sorter: reading
पढ़ना (1/4): 'अक्षर' स्तर पर लगभग कितने बच्चे हैं? मोटा अंदाज़ा काफ़ी है; किसी बच्चे का नाम लिखने की ज़रूरत नहीं।
   buttons: [0] | [1-5] | [6-10] | [11-20] | [20+]

--- sorter: result
पढ़ना: आपके अंदाज़े के हिसाब से कक्षा को 3 समूहों में बाँटा जा सकता है। यह अनुमान सिर्फ़ इस बातचीत में है, कोई जानकारी दर्ज नहीं होती।
सबसे पहले समूह 1 के साथ बैठें: ये बच्चे सबसे ज़्यादा सहारे वाले स्तर पर हैं, और पुस्तिका अधिक सहायता वाले बच्चों के साथ अलग से काम करने को कहती है।
स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 135 (राज्य: उ.प्र.)
   [source chip: स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 135 (राज्य: उ.प्र.)]
समूह 1: अक्षर (6-10 बच्चे)
10 मिनट की गतिविधि: अक्षर कार्ड या ग्रिड बनाकर दें। आप एक अक्षर बोलें और बच्चे सही अक्षर पर उँगली रखें। फिर उसी अक्षर को शब्दों में ढूँढकर गोला लगवाएँ।
स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 136 (राज्य: उ.प्र.)
स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 134 (राज्य: उ.प्र.)
   [source chip: स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 136 (राज्य: उ.प्र.)]
   [source chip: स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 134 (राज्य: उ.प्र.)]
समूह 2: शब्द (11-20 बच्चे)
10 मिनट की गतिविधि: परिचित अक्षरों की ग्रिड पर दो-दो अक्षर जोड़कर तेज़ी से बोलें और बच्चों को साथ बोलने दें। जब वे सहज हो जाएँ, तो अक्षर जोड़कर शब्द बनवाएँ, पढ़वाएँ और लिखवाएँ।
स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 136 (राज्य: उ.प्र.)
स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 137 (राज्य: उ.प्र.)
   [source chip: स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 136 (राज्य: उ.प्र.)]
   [source chip: स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 137 (राज्य: उ.प्र.)]
समूह 3: अनुच्छेद (1-5 बच्चे)
10 मिनट की गतिविधि: पहले आप पाठ को हाव-भाव के साथ पढ़कर सुनाएँ। फिर बच्चे जोड़ियों या समूह में बारी-बारी से वही पाठ पढ़ें और आप सबको अलग-अलग सुझाव दें।
स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 140 (राज्य: उ.प्र.)
   [source chip: स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 140 (राज्य: उ.प्र.)]
एक कमरे में कई कक्षाएँ हों तो: अगर एक ही कमरे में कक्षा 1 और 2 साथ बैठती हैं, तो पुस्तिका में दोनों कक्षाओं के पीछे रह रहे बच्चों का एक ही समूह बनाकर उसके साथ रिमीडियल काम करने का उदाहरण दिया गया है।
स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 139 (राज्य: उ.प्र.)
स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 140 (राज्य: उ.प्र.)
   [source chip: स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 139 (राज्य: उ.प्र.)]
   [source chip: स्रोत: भाषा संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 140 (राज्य: उ.प्र.)]
इनमें से किसी गतिविधि के बारे में और जानना हो तो हैंडबुक से पूछिए।
   buttons: [हैंडबुक से पूछें]
```

## 2:30 to 2:50. Cluster meeting pack (trainer.demo)

Screen: log in as `trainer.demo`, scroll to **संकुल बैठक पैक**, open the printable agenda. Say: "Counts only, from
consenting teachers, hidden below ten. The cluster ARP login shows the privacy rule instead: that demo cluster has
seven consenting teachers, so nothing is shown."

Expected card (counts are the seeded demo data, labelled as such):

```
संकुल बैठक पैक
डेमो डेटा: ये कक्षा-जाँचें काल्पनिक डेमो शिक्षकों की हैं, वास्तविक शिक्षकों की नहीं।
1. हासिल वाला घटाव गलत करते हैं (बंडल खोलना): बच्चे अटकते हैं, 14 शिक्षकों ने बताया
   साथ में अभ्यास: हासिल वाला घटाव: बंडल खोलकर
2. हासिल वाला जोड़ गलत करते हैं: बच्चे अटकते हैं, 11 शिक्षकों ने बताया
   साथ में अभ्यास: हासिल वाला जोड़: 10 तीलियों का बंडल बनाकर
```

The agenda is one page: 5 मिनट share, 15 मिनट practise
the move together, 10 मिनट read the handbook tip, 5 मिनट each
teacher picks one thing to try.

## 2:50 to 3:00. Close

Say: "Built: these seven pieces, tested. Not built: regional languages, a WhatsApp pilot, any measure of learning."
(Fuller pilot wording is in `docs/submission/PITCH_NOTES.md`; it does not fit in ten seconds.)

## Rehearsal notes

- Cold start on Render free: open `/healthz` a minute early.
- A1/A2/B chips appear only after 30 s idle in a subtraction scene. Type or speak the lines; do not wait for them.
- The strip shows "अटका हुआ · फिर अटका" after a told answer followed by a new problem on which Ravi gives the bug
  answer again. It reads that from the turn history; with no turn history it shows plain "अटका हुआ".
- If the hosted act tagger tags a line differently, say so and move on; the engine's numbers stay the same.

## Timing: 3:00 total, spoken words per section

Spoken words are the quoted "Say" lines only; at about 2 to 2.5 words a second the hook is the one section that runs fast, and a human should trim it or let the voice-over run over the screen.

| Section | Window | Spoken words |
|---|---|---|
| Problem hook | 0:00 to 0:20 | 72 |
| Check-in | 0:20 to 0:55 | 16 |
| Hero beat | 0:55 to 1:35 | 40 |
| Feedback | 1:35 to 2:05 | 24 |
| Level sorter | 2:05 to 2:30 | 17 |
| Cluster pack | 2:30 to 2:50 | 28 |
| Close | 2:50 to 3:00 | 16 |
