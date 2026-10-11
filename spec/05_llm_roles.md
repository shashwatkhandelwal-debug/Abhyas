# 05 — Claude roles, prompts, schemas, guards

All Claude calls go through `llm/client.py`. Each role lives in `llm/roles/<role>.py` and exposes one async function returning a validated pydantic object **or** a deterministic fallback. Prompts live in `llm/prompts/<role>.v1.md` and are loaded at startup; the version string is logged per call.

## 5.1 Client (`llm/client.py`)

```python
async def call_tool(
    role: str, model: str, system: str, messages: list[dict],
    tool_name: str, input_schema: dict,            # JSON Schema from the pydantic model
    temperature: float, max_tokens: int, timeout_s: float,
) -> dict: ...
```

- Uses Anthropic Messages API with `tools=[{name, description, input_schema}]` and `tool_choice={"type": "tool", "name": tool_name}`; returns the tool `input` dict.
- `system` is passed as a content block with `cache_control: {"type": "ephemeral"}` (prompt caching for the static role prompt + move card).
- Timeout `LLM_TIMEOUT_SECONDS` (8 s runtime roles, 60 s build-time). On timeout/5xx/overload: **one** retry (`LLM_MAX_RETRIES = 1`), then raise `LLMUnavailable`.
- Logs a row to `llm_call` (role, prompt_version, model, tokens incl. cache reads, latency, outcome).
- `MockLLM` (selected when `ANTHROPIC_API_KEY` is empty or `LLM_PROVIDER=mock`) returns golden outputs from `backend/tests/golden/<role>/*.json` keyed by a hash of the input, or a schema-valid default. **The whole product must run end-to-end on MockLLM.**

Model routing (env):

| Env var | Default | Roles |
|---|---|---|
| `CLAUDE_MODEL_FAST` | `claude-haiku-5-5` | intent_router, act_tagger, child_voice, question_classifier |
| `CLAUDE_MODEL_SMART` | `claude-sonnet-5-5` | coach, fidelity_checker, guide_answerer |
| `CLAUDE_MODEL_BUILD` | `claude-sonnet-5-5` | move_generator, move_reviewer, model_teacher, page_ocr |

Temperatures: scoring/tagging roles 0.0; child_voice 0.4; guide_answerer 0.2; build-time 0.3.

## 5.2 Role contract pattern (every runtime role)

```
build_input()  →  call_tool()  →  pydantic.validate  →  guard(input, output)
     ↘ on ValidationError / GuardError: retry once with the error message appended ("Your previous output failed: <reason>. Fix it.")
     ↘ on second failure or LLMUnavailable: fallback() (deterministic), log guard_failure (+ review_item if role is scoring)
```

Guard functions live in `llm/guards.py`, are pure, and are unit-tested with good/bad fixtures.

---

## 5.3 `intent_router` (fast) — what did the teacher mean?

Called only when keyword intents (08 › 8.3) don't match and the state is not REHEARSE (in REHEARSE, everything is talk-to-children unless a keyword/button says otherwise).

**Output schema**
```json
{"intent": "answer_for_step | question | command_next | command_skip | command_repeat | command_help | smalltalk | unclear",
 "confidence": 0.0}
```
**Guard:** enum valid. `confidence < 0.5` → treat as `answer_for_step` if the current state expects free speech (EXPLAIN_BACK, REFLECT), else `unclear`.
**Fallback:** `answer_for_step` for EXPLAIN_BACK/REFLECT, else `unclear` (send help menu).

**Prompt `intent_router.v1.md`**
```
You route messages from a Hindi-speaking government primary-school teacher using Abhyas, a practice app.
The teacher is currently at step: {state} — {state_description_hi}.
The app expects at this step: {expected_input}.

Classify the teacher's latest message (Hindi, Hinglish or English; it may be a speech-to-text transcript with errors):
- answer_for_step: she is doing what this step expects (explaining the move, answering reflection questions, giving profile info).
- question: she is asking a question about teaching, her classroom, children, materials, or admin.
- command_next / command_skip / command_repeat / command_help: she wants to move on, skip, hear again, or get help.
- smalltalk: greetings, thanks, unrelated chat.
- unclear: you cannot tell.
Return only the tool call.
```

---

## 5.4 `act_tagger` (fast) — what teaching acts did the teacher use?

**Input:** transcript of one teacher turn; scene context (move title, current item, children names + ids + their last line), act taxonomy with Hindi examples.

**Output schema**
```json
{"acts": ["ask_to_explain", "..."],
 "addressed_child": "ravi | priya | aman | all | null",
 "problem": {"type": "sub|add|place_value|read_word", "a": 0, "b": 0, "tens": 0, "ones": 0, "word": ""} ,
 "quote": "exact substring of the transcript that shows the main act"}
```
`problem` is null unless the teacher poses a *new* item.

**Guards:** every act ∈ taxonomy (14 values); ≤ 4 acts; `addressed_child` ∈ scene persona ids ∪ {"all", null}; `quote` is a normalised substring (5.10) of the transcript or empty; if `problem` present, its numbers/word appear in the transcript (digits, Devanagari digits or Hindi number words — use `hindi_numbers.py`).
**Fallback:** keyword tagger (`rule_engine` independent, in `llm/roles/act_tagger.py`): regex over normalised transcript —
`क्यों|कैसे|बताओ|समझाओ|how|why|explain` → ask_to_explain; `बंडल|तीली|गड्डी|bundle|stick` → concrete_representation; `सही उत्तर .* है|answer is|उत्तर \d+ है` → tell_answer; `शाबाश|बहुत अच्छा कोशिश|good try` → praise_effort; `चुप|ध्यान दो|गलत है ना` (harsh) → scold; `ध्वनि|आवाज़ निकालो|अ-क्ष-र` → phonics_sound_out; `दोनों उत्तर|किसका सही` → contrast_answers; `धीरे-धीरे करके देखो|मैं करके दिखाती` → model_step_aloud; `छोटी संख्या|पहले \d+ से` → probe_simpler_case; child name match → addressed_child. If nothing matches → `repeat_question`.

**Prompt `act_tagger.v1.md`**
```
You label what a teacher did in ONE turn of a classroom role-play. Three simulated Class 2 children are in the scene.
You do NOT decide how children respond. You ONLY label the teacher's turn.

Move being practised: {move_title_hi}
Current problem on the board: {current_item_text}
Children: {children_list}   (id, name, last thing they said)

Teaching-act taxonomy (use only these ids):
- ask_to_explain: asks a child HOW/WHY they got their answer ("कैसे किया?", "समझाओ", "बताओ तुमने क्या सोचा")
- concrete_representation: uses or asks to use bundles/sticks/objects/fingers/drawings ("10-10 तीलियों के बंडल", "गिनकर देखो")
- probe_simpler_case: gives an easier related problem to test understanding ("पहले 12 में से 7 करके दिखाओ")
- contrast_answers: puts two answers side by side and asks which is right / why ("रवि ने 45 कहा, प्रिया ने 35 — किसका सही?")
- model_step_aloud: teacher demonstrates the procedure step by step aloud
- tell_answer: teacher states the correct answer herself
- repeat_question: repeats or rephrases the same question without new support
- praise_effort: praises the child's effort or thinking ("अच्छा सोचा", "कोशिश बढ़िया थी")
- praise_generic: generic praise without content ("शाबाश", "वेरी गुड")
- scold: harsh or shaming words ("इतना भी नहीं आता?", "चुप रहो")
- involve_peer: asks another child to respond to / explain to a classmate
- phonics_sound_out: asks to sound out letters/aksharas or blends them aloud ("म-े… मे, ला… मेला")
- off_task: talk unrelated to the lesson
- give_new_problem: poses a new problem/word
Rules:
1. A turn can contain several acts; list all that clearly apply (max 4), most important first.
2. addressed_child: the child spoken to by name or clear reference; "all" if addressing the class; null if unclear.
3. If the teacher poses a new item, fill "problem" exactly from her words (numbers may be spoken in Hindi words: "बावन" = 52). Otherwise null.
4. quote: copy the exact words from the transcript that show the most important act.
5. The transcript comes from speech recognition and may contain errors. Be charitable but do not invent acts.
```
Include in the system prompt (cached) 2 worked examples per act from `content/act_examples_hi.yaml` (agent writes ~30 examples; include the Ravi example).

---

## 5.5 `child_voice` (fast) — render the engine's result as one child's line

**Input:** persona (name, age 7, temperament, `speech_style_hi`, `off_topic_lines_hi`), `ChildResponse` (kind, answer, steps with `text_hi`, affect, item), last 4 lines of the scene.

**Output schema**
```json
{"line_hi": "string"}
```

**Guards (`guard_child_line`)** — all must pass:
1. Length: 1–`MAX_CHILD_LINE_WORDS` (25) words; SILENT kind → must be empty string (we render "(प्रिया चुप है)" ourselves).
2. **Numbers:** extract every number in the line (Arabic digits, Devanagari digits ०-९, Hindi number words 0–100 such as "पैंतालीस", "पैंतीस", "बावन", "सत्रह", and "एक/दो/तीन…"). Every number ∈ `allowed_numbers`. For ANSWER/EXPLAIN_BUG/RELAPSE/SCAFFOLDED_CORRECT/CORRECT_EXPLAINED/PARROT the `answer` must appear.
3. **Forbidden:** no token in `forbidden` appears (e.g. the correct answer 35 while the child is in misconception) — check digits and number words.
4. **Literacy:** the answer string (e.g. "मल", "मछली", "मे - ला" — hyphens/spaces normalised) appears; the correct word does not appear when forbidden.
5. Stays in character: reject lines containing "AI", "assistant", more than 3 consecutive English words, or the words "गलती", "misconception", "rule", "नियम".
6. OFF_TOPIC / INTERJECT: contains no numbers at all.

**Fallback (`template_line`)**: deterministic from the response:
- ANSWER → `"{answer}!"`; EXPLAIN_BUG / RELAPSE / SCAFFOLDED_CORRECT / CORRECT_EXPLAINED → join `steps[*].text_hi` with "। " then `"। {answer}!"`; PARROT → `"{answer}… ?"`; SILENT → `""`; OFF_TOPIC/INTERJECT → `persona.off_topic_lines_hi[turn_idx % len]`; CONFUSED → `"दीदी, ये तो बहुत बड़ा है… समझ नहीं आया।"`. Prefix "हम्म… " for SCAFFOLDED_CORRECT.

**Prompt `child_voice.v1.md`**
```
You voice ONE line spoken by a 7-year-old child in a government primary school in Uttar Pradesh, in simple spoken Hindi (Devanagari).
You are an actor reading a script: the CONTENT of what the child says is already decided by a rule engine. You only choose natural words.

Child: {name} — temperament: {temperament}. Style: {speech_style_hi}. Affect now: {affect}.
What the child says this turn (kind = {kind}):
- answer: {answer}
- reasoning steps to express (in this order, may be shortened, keep every number): {steps_text}

Hard rules:
1. Use ONLY these numbers: {allowed_numbers}. You MUST say the answer {answer}. NEVER say {forbidden}.
2. At most 25 words. One or two short sentences. Address the teacher as "{teacher_address}".   # "दीदी"/"मैडम" if address_form f, "सर" if m (persona off-topic lines get the same substitution in code)
3. kind=answer: just the answer, confidently, no explanation.
   kind=explain_bug: explain the steps as if they are obviously right (the child believes them).
   kind=relapse: same as explain_bug (the child forgot what was taught).
   kind=scaffolded_correct: hesitant, thinking aloud, arrives at the answer.
   kind=correct_explained: confident and explains why.
   kind=parrot: just repeats the answer with a questioning tone, no reasoning.
   kind=off_topic / interject: one short unrelated childlike remark, no numbers.
4. Shy children speak very little. Distracted children may trail off. Confident children speak fast.
5. Never correct yourself beyond what the steps say. Never mention rules, mistakes, AI, or learning.
Return only the tool call.
```

---

## 5.6 `coach` (smart) — rubric feedback after a scene

**Input:** move (title, rubric criteria with level descriptors, `teaching_acts_effective`), full scene transcript as numbered lines (`T1 teacher: …`, `T1 ravi: …`), act tags per teacher turn, child state trajectories, attempt number, previous attempt's `change_hi` (if retry).

**Output schema**
```json
{"scores": {"<criterion_id>": 0},
 "evidence": {"<criterion_id>": "exact teacher quote or '' if score is 0 for absence"},
 "strength_hi": "one sentence",
 "change_hi": "one sentence",
 "exact_words_hi": "a sentence the teacher can literally say next time",
 "improved_since_last": true,
 "confidence": 0.0}
```

**Guards:** keys of `scores` == rubric criterion ids exactly; values ∈ {0,1,2}; for every score > 0 the evidence is a normalised substring (5.10) of a **teacher** line; strength/change/exact_words each a single sentence (≤ 1 "।"/"." inside, excluding the end) and the three together ≤ `MAX_COACH_FEEDBACK_WORDS` (60) words; respectful register (must use "आप"/"आपने", must not use "तुम"/"तुमने"); `exact_words_hi` must not contain the correct answer to the current item if the move's rubric rewards not telling the answer.
**Confidence:** `< COACH_CONFIDENCE_THRESHOLD` (0.6) → still send (with lighter framing message `coach_low_conf_prefix`), set `needs_review`, create `review_item`.
**Fallback (deterministic coach):** score each criterion from act tags: criterion has `signal_acts` in the move YAML (e.g. `crit_explaining: [ask_to_explain]`) → 2 if a signal act occurred and the target child advanced, 1 if occurred without advancement, 0 otherwise; strength/change/exact_words from the move's `feedback_bank` keyed by criterion. Mark `confidence = 0.3`, `needs_review = true`.

**Prompt `coach.v1.md`**
```
You are an experienced, kind FLN (foundational literacy and numeracy) coach in Uttar Pradesh giving feedback to a government primary teacher, colleague to colleague, in simple Hindi. The teacher just rehearsed a teaching move with three simulated children.

Move: {move_title_hi}
What good practice looks like (the effective acts for this move): {effective_acts_hi}
Rubric (score each criterion 0, 1 or 2 using the descriptors):
{rubric_block}

Transcript (teacher turns are labelled "teacher"; child lines were generated by a rule engine and are realistic):
{transcript}
Teaching acts detected per teacher turn: {acts_block}
How each child's understanding changed: {trajectory_block}
{retry_block}   # e.g. "Last attempt you asked her to change: …. Say whether she did."

Instructions:
1. Score every criterion. For each score above 0, copy the teacher's EXACT words as evidence (from teacher lines only).
2. strength_hi: ONE specific thing she did well, quoting or pointing to her words. Start with "आपने…".
3. change_hi: ONE most important change for the next attempt. Concrete, not generic.
4. exact_words_hi: ONE sentence she can literally say to the child next time, in natural classroom Hindi.
5. Total of the three sentences ≤ 60 words. Respectful "आप" register. Never shame. No English jargon.
6. confidence: your confidence that the scores match what an expert FLN coach would give (0–1). Lower it if the transcript is short, garbled, or ambiguous.
```

---

## 5.7 `fidelity_checker` (smart) — explain-it-back scoring

**Input:** move key points (`id`, `text_hi`, `must_have`), the teacher's explanation transcript.

**Output schema**
```json
{"points": [{"id": "kp1", "status": "covered|partial|missing", "quote": ""}],
 "misconceptions": ["short Hindi description of anything she said that contradicts the module"],
 "confidence": 0.0}
```
**Guards:** one entry per key point id, no extras; `covered|partial` require a quote that is a normalised substring of the transcript (fuzzy ≥ 90, 5.10); `missing` requires empty quote; misconceptions ≤ 3, each ≤ 25 words.
**Reply composition (code, not LLM):** "धन्यवाद! आपने {n_covered} में से {n_total} मुख्य बातें कहीं।" + if any must_have missing: "एक बात और याद रखें: {first missing must_have text_hi}" + if misconception: "ध्यान दें: {misconceptions[0]}".
**Fallback:** keyword overlap per key point (each key point has `keywords_hi` in YAML; ≥ 50% present → covered, ≥ 25% → partial), confidence 0.3, needs_review.

**Prompt `fidelity_checker.v1.md`**
```
A government primary teacher has just listened to a 2-minute explanation of a teaching move and explained it back in her own words (speech-to-text transcript, may contain recognition errors).
Judge, for each key point below, whether she covered it (same meaning, own words are fine), partially covered it, or missed it.
Key points:
{key_points_block}
Teacher's explanation:
"""{transcript}"""
Rules: For covered/partial, copy the exact words from her explanation that show it. Do not give credit for vague statements. List any statement that contradicts the key points as a misconception (Hindi, short). confidence: 0–1.
```

---

## 5.8 `question_classifier` (fast) + `guide_answerer` (smart) — Ask any time

**question_classifier output**
```json
{"category": "pedagogy | classroom_management | admin | out_of_scope",
 "needs_clarification": false,
 "clarifying_question_hi": "",
 "search_query_hi": "short Hindi keyword query for the guides",
 "confidence": 0.0}
```
Guard: if `needs_clarification` then `clarifying_question_hi` non-empty and ≤ 20 words; ask at most **one** clarifying question per question thread (`question.clarifying_asked`).
out_of_scope → polite canned reply (`ask_out_of_scope`), no retrieval. admin → canned "यह जानकारी आपके BEO/ARP कार्यालय से मिलेगी" + escalate to ARP.

**guide_answerer input:** question, category, top-k (`RETRIEVAL_TOP_K` = 5) chunks with ids, source short names, section, page.
**Output schema**
```json
{"answer_hi": "", "source_ids": ["chunk-id"], "try_this_week_hi": "", "confidence": 0.0}
```
**Guards:** `source_ids` non-empty and ⊆ retrieved ids; answer ≤ `MAX_GUIDE_ANSWER_WORDS` (80) words; no numbers/claims of policy unless present in a cited chunk (heuristic: every number in answer appears in a cited chunk); respectful register.
**Escalation:** if no chunk scores ≥ `RETRIEVAL_MIN_SCORE` or confidence < `GUIDE_CONFIDENCE_THRESHOLD` (0.6) or guard fails twice → reply `ask_escalated` ("मैं आपके ARP से पूछकर बताती हूँ…"), create `review_item(kind='question')`, add to ARP digest.
**Reply composition:** answer + "स्रोत: {source_short_hi}, पृष्ठ {page}" + try_this_week + schedule follow-up job at +48 h.

**Prompt `guide_answerer.v1.md`**
```
You answer a government primary teacher's question using ONLY the official guide excerpts below. Answer in simple, respectful Hindi (आप), ≤ 80 words, practical, for a real classroom with few materials, multi-grade classes and irregular attendance.
If the excerpts do not contain the answer, set confidence below 0.4 and say so briefly — do not invent.
Question ({category}): {question}
Excerpts:
{chunks_block}   # [chunk-id] (source, section, page): text
Return: answer_hi; source_ids you actually used; try_this_week_hi = one small action she can try this week (≤ 20 words); confidence.
```

---

## 5.9 Build-time roles (content pipeline, 10)

| Role | Input | Output | Guard |
|---|---|---|---|
| `move_generator` | source chunks for one topic, move schema, an approved example move | full move YAML as JSON (schema in 10) | JSON Schema valid; every key point has `source_chunk_ids` ⊆ given; scenario items computed by rule engine (validator recomputes); Hindi NFC; lengths |
| `move_reviewer` | generated move + source chunks + rubric for content quality | `{issues: [{field, severity, note_hi}], approve_recommendation}` | schema |
| `model_teacher` | move, scenario, persona list | `model_rehearsal` script lines (teacher lines + act ids); **child lines are then generated by running the rule engine + child_voice**, never by this role | teacher lines' acts must be effective acts; script ends with all children CORRECT when run through the engine |
| `page_ocr` | page image (PNG) of a Hindi PDF whose text layer is garbled (legacy fonts like Kruti Dev) | `{text_hi}` | Devanagari ratio ≥ 0.6 |

Prompts for these: write them in `llm/prompts/` following the same style; include the approved seed move `NUM_SUB_REGROUP_BUNDLES` as the few-shot example.

## 5.10 Text normalisation for guards (`llm/guards.py › norm`)

`norm(s)`: NFC → lowercase Latin → Devanagari digits → Arabic → strip punctuation `।,.!?;:"'()-–—` → collapse whitespace → remove nukta variants (ड़→ड़ canonical) → remove zero-width joiners.
Substring check: `norm(quote) in norm(source)`; if false, `rapidfuzz.fuzz.partial_ratio(norm(quote), norm(source)) ≥ QUOTE_FUZZY_MIN` (90).

`hindi_numbers.py`: `extract_numbers(text) -> list[int]` handling Arabic digits, Devanagari digits, and Hindi number words 0–100 (full table: शून्य, एक, दो, तीन, चार, पाँच/पांच, छह/छः, सात, आठ, नौ, दस, ग्यारह, बारह, तेरह, चौदह, पंद्रह/पन्द्रह, सोलह, सत्रह, अठारह, उन्नीस, बीस, इक्कीस … निन्यानवे, सौ — include common spelling variants and Roman Hinglish: "paintalis", "paintees", "baawan", "satrah", etc. for the numbers used in seed content at least). Exhaustively unit-test 0–100 Devanagari words.

## 5.11 Golden tests (`backend/tests/golden/`)

For each runtime role, ≥ 5 input→output JSON fixtures (written by hand, checked by a team member) used by MockLLM and by `test_guards.py` (good outputs pass, deliberately bad variants fail with the expected guard). `make test-live` re-runs the inputs against real Claude and asserts guard pass rate ≥ 90%.
