# 04 — Rule engine (core IP)

**Principle: children's mistakes are computed, not improvised.** LLMs asked to play students tend to answer correctly or give in too fast (Markel et al., 2023, "GPTeach"; arXiv 2605.12748, 2026). So every simulated child's answer, reasoning steps and state change come from **pure, deterministic Python** in `backend/app/rule_engine/`. Claude only *voices* the result (05 › child_voice), and a guard rejects any line whose numbers/words the engine did not produce.

`rule_engine/` must not import anything outside itself (no DB, no LLM, no I/O). 100% branch coverage target.

## 4.1 Types

```python
class Domain(str, Enum): NUMERACY = "numeracy"; LITERACY = "literacy"

class Problem(BaseModel):                      # an item the children work on
    type: Literal["sub", "add", "place_value", "read_word"]
    a: int | None = None                       # sub/add: a − b or a + b (two-digit)
    b: int | None = None
    tens: int | None = None                    # place_value: bundles of 10
    ones: int | None = None                    #              loose sticks
    word: str | None = None                    # read_word (Devanagari, NFC)
    def key(self) -> str: ...                  # stable id e.g. "sub:52-17", "pv:4-7", "word:मेला"

class Step(BaseModel):                         # one reasoning step, engine-rendered
    code: str                                  # e.g. "SUB_CANNOT", "SUB_SWAP", "REGROUP_OPEN_BUNDLE"
    nums: list[int] = []                       # every number mentioned in this step
    words: list[str] = []                      # every Hindi word token that must appear (literacy)
    text_hi: str                               # rendered template (digits as Arabic numerals)

class BugOutput(BaseModel):
    rule_id: str
    answer: int | str
    steps: list[Step]

class ChildState(IntEnum):
    MISCONCEPTION = 0   # applies bug, confident, no explanation
    CAN_EXPLAIN   = 1   # still wrong, explains steps (reveals the bug)
    PARTIAL       = 2   # correct with scaffold on the current item; may relapse on a new item
    CORRECT       = 3   # correct and explains why, on any item

class ChildRuntime(BaseModel):
    persona_id: str
    misconception: str                         # bug rule id assigned by the scenario
    temperament: Literal["confident", "shy", "distracted"]
    state: ChildState = ChildState.MISCONCEPTION
    partial_item_key: str | None = None        # item on which PARTIAL was reached
    silent_turns: int = 0
    turns_since_addressed: int = 0
    last_answer: int | str | None = None
    history: list[tuple[int, ChildState]] = [] # (teacher_turn_idx, state) trajectory

class SceneState(BaseModel):
    move_id: str
    domain: Domain
    effective_acts: list[str]                  # from move.teaching_acts_effective
    target_causes: list[str]
    items: list[Problem]                       # scenario items (in order)
    item_idx: int = 0
    current_item: Problem
    children: list[ChildRuntime]               # exactly 3 in normal mode, 1 in placement mode
    teacher_turns: int = 0
    last_responder: str | None = None
    ended: bool = False
    end_reason: str | None = None

class TaggedTurn(BaseModel):                   # from act_tagger (05), validated
    acts: list[TeachingAct]
    addressed_child: str | None                # persona id | "all" | None
    problem: Problem | None                    # if the teacher posed a new item

class ResponseKind(str, Enum):
    ANSWER = "answer"                          # MISCONCEPTION: bug answer, no steps
    EXPLAIN_BUG = "explain_bug"                # CAN_EXPLAIN: bug answer + bug steps
    SCAFFOLDED_CORRECT = "scaffolded_correct"  # PARTIAL: correct answer, hesitant, correct steps
    RELAPSE = "relapse"                        # PARTIAL on a new item without support: bug again
    CORRECT_EXPLAINED = "correct_explained"    # CORRECT
    PARROT = "parrot"                          # repeats the told answer, no understanding
    SILENT = "silent"                          # shy child after scolding
    OFF_TOPIC = "off_topic"                    # distracted child
    INTERJECT = "interject"                    # unprompted distracted interjection
    CONFUSED = "confused"                      # teacher posed an out-of-scope problem

class ChildResponse(BaseModel):
    persona_id: str
    kind: ResponseKind
    answer: int | str | None
    correct_answer: int | str | None
    steps: list[Step]
    prior_state: ChildState
    new_state: ChildState
    affect: Literal["neutral", "confident", "encouraged", "upset", "shy", "distracted"]
    item: Problem
    allowed_numbers: set[int]                  # for the guard
    allowed_words: set[str]
    forbidden: set[str]                        # tokens that must NOT appear (e.g. correct answer)

class StepResult(BaseModel):
    responses: list[ChildResponse]             # 1 main + at most 1 INTERJECT
    ended: bool
    end_reason: Literal["all_correct", "turn_limit", "teacher_stop"] | None
```

## 4.2 Bug rules (`rule_engine/bugs/`)

Each rule: `def rule(problem: Problem) -> BugOutput` and a paired `correct(problem) -> BugOutput`. Registry maps id → (fn, kind, applicable problem types, description_hi, research_ref). Rules raise `NotApplicable` for wrong problem types. All arithmetic is column-wise on two-digit numbers (`10 ≤ b < a ≤ 99` for sub; `10 ≤ a, b ≤ 99` for add).

Research base for the bug families (cite in deck and `description` field): Brown & Burton (1978) and VanLehn (1990) procedural-bug studies for multi-digit subtraction/addition; Indian evidence on place-value errors from ASER and NCERT FLN materials; Hindi reading errors (matra omission, guessing from first akshar, akshar-by-akshar non-blending) from NIPUN Bharat / Pratham reading-level guidance. **HUMAN INPUT:** the FLN mentor confirms these are common in UP classrooms.

### Numeracy

| Rule id | Behaviour | 52−17 | 43−27 | 61−28 | 74−39 |
|---|---|---|---|---|---|
| (correct) | regroup | **35** | **16** | **33** | **35** |
| `SUB_SMALLER_FROM_LARGER` | each column: larger digit − smaller digit | 45 | 24 | 47 | 45 |
| `SUB_BORROW_NO_DECREMENT` | adds 10 to units, forgets to reduce tens | 45 | 26 | 43 | 45 |
| `SUB_WRITE_ZERO_WHEN_STUCK` | if top units < bottom units, writes 0 in units; tens subtracted normally | 40 | 20 | 40 | 40 |

| Rule id | Behaviour | 38+45 | 27+48 | 56+29 |
|---|---|---|---|---|
| (correct) | carry | **83** | **75** | **85** |
| `ADD_NO_CARRY` | writes the full units sum, then tens sum to its left | 713 | 615 | 715 |
| `ADD_CARRY_FORGOTTEN` | writes units digit, drops the carry | 73 | 65 | 75 |
| `ADD_CARRY_WRONG_DIGIT` | writes the tens digit of the units sum, carries the units digit | 101 | 111 | 121 |

Note `ADD_NO_CARRY`: answer is the integer formed by concatenating `str(ta+tb)` and `str(ua+ub)` (e.g. 7 and 13 → 713).
`ADD_CARRY_WRONG_DIGIT`: units sum s = ua+ub ≥ 10 → write s // 10, carry s % 10 → tens = ta+tb+(s%10) → answer = tens*10 + s//10 (38+45: s=13 → write 1, carry 3 → 3+4+3=10 → 101).

| Rule id (place value; item = tens bundles, ones sticks; question "कुल कितनी तीलियाँ?") | (4,7) | (3,5) | (6,2) |
|---|---|---|---|
| (correct) | **47** | **35** | **62** |
| `PV_BUNDLE_AS_ONE` — counts each bundle as 1 | 11 | 8 | 8 |
| `PV_CONCAT_SPOKEN` — writes "चालीस" as 40 then appends 7 → 407 | 407 | 305 | 602 |
| `PV_REVERSAL` — writes ones digit first | 74 | 53 | 26 |

When a bug does not manifest on an item (e.g. sub with no regrouping), the rule returns the correct answer with the child's normal steps; responses still work and the guard allows the correct number because it equals the bug answer.

### Literacy (item = a word)

| Rule id | Behaviour | मेला | पानी | किताब | गुड़िया |
|---|---|---|---|---|---|
| (correct) | reads the word, blends | मेला | पानी | किताब | गुड़िया |
| `MATRA_DROP` | drops all dependent vowel signs and ं ँ ः | मल | पन | कतब | गड़य |
| `FIRST_AKSHAR_GUESS` | reads first akshar, guesses a familiar word starting with the same base consonant from `guess_lexicon` (move YAML); if the guess equals the word, uses the 2nd entry | मछली | पतंग | कमल | गमला |
| `AKSHAR_BY_AKSHAR` | sounds each akshar separately, cannot blend; answer = aksharas joined by " - " | मे - ला | पा - नी | कि - ता - ब | गु - ड़ि - या |

**Akshar splitter** (`bugs/akshar.py`, own implementation — do not rely on `\X`): an akshar = (independent vowel | consonant [+ nukta] (+ virama + consonant [+ nukta])*) + optional dependent vowel sign + optional (ं|ँ|ः). Test on: किताब→[कि,ता,ब], गुड़िया→[गु,ड़ि,या], विद्यालय→[वि,द्या,ल,य], आम→[आ,म], संतरा→[सं,त,रा].

### Step templates (engine-rendered, Hindi, Arabic digits)

Implement as a dict `STEP_TEMPLATES[code] -> str.format(**vars)`; all numbers placed in `Step.nums`. Minimum set:

| code | text_hi template | used by |
|---|---|---|
| `SUB_CANNOT` | `{u_top} में से {u_bot} नहीं घटता` | all sub bugs, correct |
| `SUB_SWAP` | `तो {u_bot} में से {u_top} घटाया, {d_u} आया` | SMALLER_FROM_LARGER |
| `SUB_TENS` | `{t_top} में से {t_bot} घटाया, {d_t} आया` | all sub |
| `REGROUP_OPEN_BUNDLE` | `एक बंडल खोला, {u_new} तीलियाँ हो गईं, {t_left} बंडल बचे` | correct sub |
| `BORROW_NO_DEC` | `{u_top} के आगे 1 लगाया, {u_new} में से {u_bot} घटाया, {d_u} आया` | BORROW_NO_DECREMENT |
| `WRITE_ZERO` | `नहीं घटा तो 0 लिख दिया` | WRITE_ZERO_WHEN_STUCK |
| `ADD_UNITS` | `{ua} और {ub} जोड़े, {s} आया` | add |
| `ADD_WRITE_ALL` | `{s} पूरा नीचे लिख दिया` | NO_CARRY |
| `ADD_DROP_CARRY` | `{s} में से {s_u} लिखा` | CARRY_FORGOTTEN |
| `ADD_CARRY` | `{s_u} लिखा, 1 हासिल ऊपर रखा` | correct add |
| `ADD_WRONG_CARRY` | `{s_t} लिखा, {s_u} हासिल ऊपर रखा` | CARRY_WRONG_DIGIT |
| `ADD_TENS` | `{ta} और {tb}{carry_txt} जोड़े, {t} आया` | add |
| `PV_COUNT_BUNDLES` | `{tens} बंडल और {ones} तीलियाँ, सब गिनीं` | pv |
| `PV_BUNDLE_TEN` | `एक बंडल में 10 तीलियाँ, तो {tens} बंडल में {tens10}` | correct pv |
| `PV_CONCAT` | `{tens10} और {ones}, तो {answer} लिखा` | CONCAT_SPOKEN |
| `PV_REVERSE` | `पहले {ones} लिखा फिर {tens}` | REVERSAL |
| `READ_AKSHARS` | `{aksharas}` (words = aksharas) | AKSHAR_BY_AKSHAR, correct read |
| `READ_NO_MATRA` | `{bare}` | MATRA_DROP |
| `READ_GUESS` | `{first} से {guess}` | FIRST_AKSHAR_GUESS |
| `ANSWER` | `{answer}` | all |

## 4.3 Transition table (`rule_engine/transitions.py`)

```python
ADVANCE: dict[TeachingAct, dict[ChildState, ChildState]] = {
    ASK_TO_EXPLAIN:          {MISCONCEPTION: CAN_EXPLAIN},
    CONCRETE_REPRESENTATION: {MISCONCEPTION: PARTIAL, CAN_EXPLAIN: PARTIAL},
    PROBE_WITH_SIMPLER_CASE: {CAN_EXPLAIN: PARTIAL},
    PHONICS_SOUND_OUT:       {MISCONCEPTION: PARTIAL, CAN_EXPLAIN: PARTIAL},
    CONTRAST_TWO_ANSWERS:    {PARTIAL: CORRECT},
    MODEL_STEP_ALOUD:        {PARTIAL: CORRECT},
    INVOLVE_PEER:            {CAN_EXPLAIN: PARTIAL},   # only when the peer who explains is CORRECT (see rule 3d)
}
NON_ADVANCING = {TELL_ANSWER, REPEAT_QUESTION, PRAISE_EFFORT, PRAISE_GENERIC, SCOLD, OFF_TASK, GIVE_NEW_PROBLEM}
```

Add `GIVE_NEW_PROBLEM = "give_new_problem"` to the `TeachingAct` taxonomy (14 acts total).

## 4.4 `RuleEngine.step(scene, tagged) -> StepResult` — exact algorithm

Deterministic. Same inputs → same outputs. No randomness anywhere.

1. **Turn count.** `scene.teacher_turns += 1`.
2. **New item.** If `tagged.problem` is not None:
   - validate: type matches scene domain; sub `10 ≤ b < a ≤ 99`; add `10 ≤ a,b ≤ 99` and `a+b ≤ 199`; pv `1 ≤ tens ≤ 9, 0 ≤ ones ≤ 9`; word: 1–4 aksharas Devanagari only.
   - valid → `scene.current_item = problem`; implicitly add `GIVE_NEW_PROBLEM` to acts.
   - invalid → main response `CONFUSED` from the responder (step 3), no state changes; go to step 8.
   - If `TELL_ANSWER` is also in acts, the PARROT response uses the item **before** the switch, and the new item becomes current at the end of this turn (so the relapse shows on the next turn).
   - If `GIVE_NEW_PROBLEM` is in acts but `problem` is None → advance `item_idx` (wrap) and set `current_item = items[item_idx]`.
3. **Responder.**
   a. `addressed_child` is a valid persona id → that child.
   b. else if `INVOLVE_PEER` in acts and `last_responder` set → next child after `last_responder` in roster order (skip silent).
   c. else (`"all"` or None) → first child, in priority order **confident → distracted → shy**, whose state < CORRECT and silent_turns == 0; **shy children are never chosen unless directly addressed**; if none, the confident child.
   d. `INVOLVE_PEER` advancing rule: applies to every *listening* child in CAN_EXPLAIN only if the responder's state is CORRECT after this turn.
4. **Whole-class acts.** If `addressed_child == "all"` and act ∈ {CONCRETE_REPRESENTATION, MODEL_STEP_ALOUD, PHONICS_SOUND_OUT} → apply that act's transition to **every** non-silent child whose misconception ∈ target_causes and act ∈ effective_acts (listeners update silently; set their `partial_item_key` when they reach PARTIAL); responder answers.
5. **Silence (checked before any transition).**
   - If `PRAISE_EFFORT` in acts → affect `encouraged`; set responder `silent_turns = 0`.
   - Else if responder `silent_turns > 0` → decrement, response `SILENT`, answer None, **no state change**; go to step 8.
6. **Responder transition.**
   - `effective = set(tagged.acts) ∩ set(scene.effective_acts)` (a child improves only through acts the move says address its cause, **and** only if `child.misconception ∈ scene.target_causes`).
   - If `SCOLD` in acts → no advancement this turn; if temperament == shy → set `silent_turns = SHY_SILENT_TURNS` (config, 1), response `SILENT` for this turn, go to step 8; else affect `upset` and continue to step 7 with state unchanged.
   - Else `new_state = max([state] + [ADVANCE[a].get(state, state) for a in effective if a in ADVANCE])` — **at most one table lookup per act from the current state** (no chaining within a turn).
   - If new_state == PARTIAL and prior < PARTIAL → `partial_item_key = current_item.key()`.
7. **Answer.** By (new) state:
   - `TELL_ANSWER` in acts and new_state == prior_state → `PARROT`: answer = correct, steps = [], **state unchanged**.
   - `OFF_TASK` in acts and temperament == distracted → `OFF_TOPIC` (answer None).
   - MISCONCEPTION → `ANSWER`: bug answer, steps [] (only `ANSWER` step).
   - CAN_EXPLAIN → `EXPLAIN_BUG`: bug answer + bug steps.
   - PARTIAL → if `current_item.key() != partial_item_key` and `effective` is empty → `RELAPSE` (bug answer + bug steps); else `SCAFFOLDED_CORRECT` (correct + correct steps); when SCAFFOLDED_CORRECT on a new item with effective support, set `partial_item_key` to the new item.
   - CORRECT → `CORRECT_EXPLAINED`: correct + correct steps.
   - `REPEAT_QUESTION` only → same kind/answer as last time (recomputation gives the same result by determinism).
8. **Allowed / forbidden sets** (for the guard):
   - `allowed_numbers` = operands (a, b or tens, ones, 10) ∪ {answer if int} ∪ all `step.nums` ∪ {1} (for "एक बंडल"/"1 हासिल").
   - `forbidden` = {str(correct_answer)} if kind ∈ {ANSWER, EXPLAIN_BUG, RELAPSE} and correct ≠ bug answer; for literacy, forbidden = {correct word} likewise.
   - `allowed_words` (literacy) = answer tokens ∪ step words.
9. **Bookkeeping.** responder `turns_since_addressed = 0`, `last_answer = answer`, append `(turn, state)` to history; `scene.last_responder = responder`. Every other child: `turns_since_addressed += 1`.
10. **Distracted interjection.** If any distracted non-responder has `turns_since_addressed ≥ DISTRACTED_INTERJECT_AFTER` (config, 3) → append one `INTERJECT` response for that child and reset its counter. Max one per turn.
11. **End.** all children CORRECT → `all_correct`; else `teacher_turns ≥ MAX_TURNS_PER_REHEARSAL` (8) → `turn_limit`. (`teacher_stop` is set by the caller when the transcript matches a stop word: बस, रुको, stop, खत्म.)

Placement mode: 1 child (Ravi, `SUB_SMALLER_FROM_LARGER`, item 52−17), 2 teacher turns, then end. Record which acts the teacher used (feeds `sessions/path.py`).

## 4.5 Required tests (`backend/tests/unit/test_rule_engine.py`, `test_bugs.py`, `test_akshar.py`)

1. **Every table cell in 4.2** as a parametrised test (bug answers + correct answers).
2. **Ravi worked example (spec-mandated):** scene for `NUM_SUB_REGROUP_BUNDLES`, Ravi = `SUB_SMALLER_FROM_LARGER`, item 52−17.
   - Turn 1: acts [ASK_TO_EXPLAIN], addressed ravi → kind EXPLAIN_BUG, answer 45, new_state CAN_EXPLAIN, `{2, 7, 5, 1, 4, 45} ⊆ allowed_numbers`, `"35" ∈ forbidden`.
   - Turn 2: acts [CONCRETE_REPRESENTATION], addressed ravi → SCAFFOLDED_CORRECT, answer 35, state PARTIAL.
   - Turn 3: acts [CONTRAST_TWO_ANSWERS] → CORRECT_EXPLAINED, state CORRECT.
3. **Relapse after tell:** Ravi MISCONCEPTION, item 52−17, acts [TELL_ANSWER] → PARROT answer 35, state stays MISCONCEPTION. Next turn problem 43−27, acts [] addressed ravi → ANSWER 24.
4. **PARTIAL relapse:** Ravi PARTIAL on 52−17; problem 61−28 with acts [] → RELAPSE 47; same but acts [CONCRETE_REPRESENTATION] → SCAFFOLDED_CORRECT 33.
5. **Ineffective acts never advance:** for move with effective = {ASK_TO_EXPLAIN, CONCRETE_REPRESENTATION, CONTRAST_TWO_ANSWERS, PROBE_WITH_SIMPLER_CASE}, act MODEL_STEP_ALOUD on a PARTIAL child → stays PARTIAL.
6. **Shy/scold:** turn 1 Priya (shy) addressed + SCOLD → SILENT, `silent_turns = 1`. Turn 2 addressed with [ASK_TO_EXPLAIN] → SILENT (counter → 0), no state change. Turn 3 addressed with [ASK_TO_EXPLAIN] → EXPLAIN_BUG. Variant: turn 2 with [PRAISE_EFFORT, ASK_TO_EXPLAIN] → silence cleared, EXPLAIN_BUG, affect encouraged.
7. **Shy never auto-selected:** addressed "all" with Ravi CORRECT, Aman CORRECT, Priya MISCONCEPTION → responder is Ravi (confident fallback), not Priya.
8. **Distracted interjection:** Aman not addressed for 3 turns → INTERJECT appended on turn 3.
9. **Whole-class concrete representation:** addressed "all" + CONCRETE_REPRESENTATION → all non-silent children move to PARTIAL.
10. **Determinism:** run a 8-turn scripted scene twice → identical serialised results.
11. **Property test (hypothesis):** for random act sequences drawn from NON_ADVANCING ∪ {acts not in effective}, no child ever reaches PARTIAL/CORRECT, and every non-PARROT answer equals the bug answer.
12. **Scene end:** all CORRECT → ended all_correct; 8 turns → turn_limit.
13. **Literacy:** all four words × three bugs; akshar splitter cases in 4.2.
14. **Serialisation:** `SceneState` round-trips through JSON (stored in `scene.engine_state`).
