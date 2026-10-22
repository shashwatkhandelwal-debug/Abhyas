# Sample inputs (five, ready to paste or speak)

Use these in the chat of **`teacher.demo2`** (one-on-one with Ravi, problem 43 − 27) unless a row says
otherwise. Speak them with the mic or paste them in the text box; the sample chips in the chat carry the same
kind of lines. Log out between experiments: the shared demo teachers reset on logout.

**How these outputs were produced.** On 2026-10-22 each input was run through the real code path
(`SceneRunner` for the scene inputs; `diagnose`; and `classify_question` → `GuideRetriever.retrieve_supported`
→ `answer_guide_question` for the question), with the real models (Haiku 5.5 for act tagging and the child's
words, Sonnet 5.5 for the answer to a question) and no speech. The fields **act, child state, kind and the
answer number** come from the rule engine and are the same on every run. The **wording of the child's line**
is the model's and can differ slightly between runs (the number in it cannot: a guard rejects any line whose
numbers are not the engine's).

## 1. A diagnosis sentence

After a scene ends and you tap retry, pick **1-1 बच्चे से बात** and a child, then say what you think the
child's mistake is:

> रवि बड़ी संख्या में से छोटी घटा देता है, उल्टा कर देता है

| Child you picked | Verdict | Why (from the run) |
|---|---|---|
| Ravi | **correct** | keyword match on his real mistake, `SUB_SMALLER_FROM_LARGER` (subtracts the smaller digit from the larger) |
| Priya | **wrong** | her real mistake is `SUB_BORROW_NO_DECREMENT`; your sentence matches a different one |
| Aman | **wrong** | his real mistake is `SUB_WRITE_ZERO_WHEN_STUCK` |

The verdict (correct / partly / wrong) is decided by fixed keyword rules; the language model is asked only
when the text matches nothing, and even then it only names a candidate that the rules then check
(`backend/app/rehearsal/diagnosis.py`, test `test_classifier_id_names_a_candidate_but_the_matcher_decides`).
After the verdict the app reveals the child's real mistake.

## 2. A "tell the answer" mistake

> रवि, सही उत्तर 16 है, इसे याद कर लो।

Actual run:

| Teacher | Act tagged | Child state | Kind / answer | Ravi says |
|---|---|---|---|---|
| रवि, सही उत्तर 16 है, इसे याद कर लो। | `tell_answer` | MISCONCEPTION (unchanged) | `parrot` / 16 | "दीदी, जवाब 16 है!" |
| अब नया सवाल: 61 में से 28। | `give_new_problem` | MISCONCEPTION | `answer` / **47** | "दीदी, जवाब 47 है! पक्का।" |

Expected behaviour: Ravi repeats the number but does not learn. On the next problem he uses his old mistake
again and answers 47 (the right answer is 33). This is the relapse the product is built around
(`test_spec_4_5_3_relapse_after_tell`).

## 3. An out-of-range problem

> रवि, 200 में से 120 घटाओ।

Actual run: act `give_new_problem`, child state unchanged, kind `confused`, no answer. Ravi says:
"दीदी, ये तो बहुत बड़ा है… समझ नहीं आया।" A problem that fails the engine's validation for the scene's number domain
(`_validate_problem` in `backend/app/rule_engine/engine.py`) gets a `confused` response and no change of state, so the
child cannot be made to "do" arithmetic the engine does not model.

## 4. A good teaching move, then a new problem

Send these three in order:

1. रवि, तुमने 43 में से 27 कैसे घटाया? एक-एक कदम बताओ।
2. देखो, ये 4 बंडल और 3 खुली तीलियाँ हैं। 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो और गिनकर बताओ।
3. बहुत अच्छा। अब ये नया सवाल खुद करो: 52 में से 17।

Actual run:

| Teacher turn | Act tagged | Child state | Kind / answer | Ravi says |
|---|---|---|---|---|
| 1 | `ask_to_explain` | CAN_EXPLAIN | `explain_bug` / 24 | "…7 में से 3 घटाया, 4 आया। फिर 4 में से 2 घटाया, 2 आया। तो जवाब 24 है!" |
| 2 | `concrete_representation` | PARTIAL | `scaffolded_correct` / 16 | "…13 में से 7 घटाया, 6 आया। फिर 3 में से 2 घटाया, 1 आया। तो जवाब 16 है!" |
| 3 | `give_new_problem` | PARTIAL | `relapse` / 45 | "…7 में से 2 घटाया, 5 आया। 5 में से 1 घटाया, 4 आया। तो जवाब 45 है!" |

Expected behaviour: asking him to explain exposes his mistake (24); the bundles move him to the right answer
(16) *with help*; on a fresh problem he slips back once (45 instead of 35) because one scaffolded success is
not yet understanding. Keep going (ask him to explain again, use the bundles, give another problem) and he
reaches CORRECT; in the ten-scene live run in `eval/one_on_one/LIVE_REPORT.md` this scene reached
CORRECT on the third and fourth turns.

## 5. A how-to question

Ask in `teacher.demo1` or `teacher.demo2` (not inside a scene):

> उल्टी गिनती करके घटाव कैसे सिखाएँ?

Actual run: classified `pedagogy`, 5 passages retrieved, answered (not escalated), with two citation lines:
"स्रोत: गणित संदर्शिका कक्षा 1 (उ.प्र.), पृष्ठ 46" and "… पृष्ठ 45". The answer, in Hindi, is: start from a
story, count back on a 1–5 line on the board (for 5 − 3 count three steps back from 5 and land on 2), let
children do it with fingers and blocks, and watch the children who cannot do it over the next two periods. It
ends with a one-line "try this week" suggestion. Tap a citation chip to read the page excerpt it came from.

Off-topic check, same box:

> आज का क्रिकेट मैच कौन जीता?

Actual run: category `out_of_scope`, nothing retrieved, no model answer; the reply is the fixed line "माफ़
कीजिए, मैं कक्षा 1-3 की पढ़ाई और कक्षा से जुड़े सवालों में ही मदद कर सकती हूँ।"

## Notes

- `teacher.demo2` starts with one teacher turn already played, so the turn counter you see is one ahead of the
  tables above, which start from a fresh scene on the same problem (43 − 27).
- The seeded Ravi scene and the chips are the same engine; there is no separate "demo mode" for children.
- If a model call fails, the child's line (or the coach's feedback) falls back to a fixed template with the
  same numbers; the table columns "kind" and "answer" do not change.
