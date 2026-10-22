"""Live one-on-one check: real Haiku (act_tagger, child_voice, diagnosis) and Sonnet (coach).

Usage: python -m eval.one_on_one_live [--max-usd 1.0] [--out eval/one_on_one/LIVE_REPORT.md]
Needs ANTHROPIC_API_KEY in the environment (never printed). Runs 10 scripted scenes
(3 moves x 3 children, plus a tell-the-answer relapse), driving the real pipeline:
diagnosis -> teacher turns (act tagger -> rule engine -> child voice) -> coach feedback.
No TTS or STT is called. Reports fallback_used rates per role, turn counts, word-cap
violations and every child line (so odd lines or placeholder leaks can be read).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.config import settings
from backend.app.llm import client as llm_client
from backend.app.llm.guards import child_line_word_cap, find_placeholder_leak
from backend.app.llm.roles.coach import coach_feedback, fallback_coach_feedback
from backend.app.llm.schemas import SceneTurn
from backend.app.rehearsal.diagnosis import DiagnosisResult, diagnose
from backend.app.rehearsal.scene_runner import SceneRunner, load_move_card
from backend.app.rehearsal.scene_store import InMemorySceneStore
from backend.app.rule_engine.domain import ChildState, ResponseKind, TeachingAct

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Scene:
    move_id: str
    child: str
    diagnosis: str
    turns: list[str]
    label: str = ""


# Teacher lines are written the way a teacher would say them (Hindi / light Hinglish); the real
# act tagger decides what act each one is.
SCENES: list[Scene] = [
    Scene(
        "NUM_SUB_REGROUP_BUNDLES",
        "ravi",
        "रवि बड़ी संख्या में से छोटी घटा देता है, उल्टा कर देता है",
        [
            "रवि, तुमने 43 में से 27 कैसे घटाया? एक-एक कदम बताओ।",
            "देखो, ये 4 बंडल और 3 खुली तीलियाँ हैं। 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो और गिनकर बताओ।",
            "तुमने पहले 24 कहा था, अब तीलियाँ गिनकर दूसरा उत्तर आया। कौन-सा सही है और क्यों?",
            "बहुत अच्छा। अब ये नया सवाल खुद करो: 52 में से 17।",
        ],
    ),
    Scene(
        "NUM_SUB_REGROUP_BUNDLES",
        "priya",
        "प्रिया ने बंडल खोला पर दहाई में से एक कम करना भूल गई",
        [
            "प्रिया, डरो मत, धीरे से बताओ, तुमने 43 में से 27 कैसे किया?",
            "चलो तीलियों से करते हैं। एक बंडल खोलो, अब कितनी खुली तीलियाँ हैं और कितने बंडल बचे?",
            "तुमने 26 कहा था। बंडल गिनकर देखो, क्या अब भी वही उत्तर आता है?",
            "शाबाश। अब ये सवाल अकेले करो: 61 में से 28।",
        ],
    ),
    Scene(
        "NUM_SUB_REGROUP_BUNDLES",
        "aman",
        "उसे समझ नहीं आया कि क्या करना है",  # vague: exercises the diagnosis classifier role
        [
            "अमन, ध्यान से सुनो। तुमने ये कैसे किया, बताओ।",
            "देखो, ये तीलियाँ हैं। 3 में से 7 नहीं निकलतीं तो बंडल खोलते हैं। तुम करके दिखाओ।",
            "तुम्हारा पहला उत्तर और अब का उत्तर अलग है। कौन सा सही है?",
            "अब ये नया सवाल: 74 में से 39, खुद करो।",
        ],
    ),
    Scene(
        "NUM_ADD_CARRY_BUNDLES",
        "ravi",
        "रवि हासिल जोड़ना भूल गया",
        [
            "रवि, तुमने 38 और 45 कैसे जोड़े? पहले इकाई में क्या किया?",
            "सब देखो: 3 बंडल 8 तीलियाँ और 4 बंडल 5 तीलियाँ। खुली तीलियाँ मिलाओ, 10 का नया बंडल बाँधो।",
            "तुमने 73 कहा था। नया बंडल कहाँ गया? बताओ कौन-सा उत्तर ठीक है?",
            "अब ये करो: 27 और 48।",
        ],
    ),
    Scene(
        "NUM_ADD_CARRY_BUNDLES",
        "priya",
        "प्रिया ने इकाई का पूरा जोड़ लिख दिया और दहाई का जोड़ आगे रख दिया",
        [
            "प्रिया, धीरे से बताओ, 713 कैसे आया?",
            "आओ बंडल बनाकर देखते हैं। 8 और 5 तीलियाँ मिलाओ, कितनी हुईं? इनसे एक बंडल बनाओ।",
            "713 और जो अब गिनकर आया, इनमें कौन-सा सही है?",
            "अब अकेले करो: 56 और 29।",
        ],
    ),
    Scene(
        "NUM_ADD_CARRY_BUNDLES",
        "aman",
        "अमन ने हासिल गलत जगह जोड़ा, 3 को हासिल बना दिया",
        [
            "अमन, 38 और 45 में तुमने पहले क्या जोड़ा?",
            "ये बंडल और तीलियाँ देखो। खुली तीलियाँ 13 हुईं, इनमें से 10 का बंडल बनाओ, कितनी बचीं?",
            "तुमने 101 कहा था। अब गिनकर दूसरा उत्तर आया, कौन-सा सही है?",
            "शाबाश, अब खुद करो: 27 और 48।",
        ],
    ),
    Scene(
        "NUM_PLACE_VALUE_BUNDLES",
        "ravi",
        "रवि ने अंक उल्टे लिख दिए, पहले इकाई का अंक लिखा",
        [
            "रवि, तुमने ये संख्या कैसे लिखी? पहले कौन-सा अंक लिखा?",
            "सब मेरे साथ गिनो। हर बंडल में 10 तीलियाँ: 10, 20, 30, 40, फिर खुली तीलियाँ गिनो।",
            "तुमने 74 कहा था और गिनकर कुछ और आया। कौन-सा सही है?",
            "अब ये करो: 3 बंडल और 5 खुली तीलियाँ कितनी हुईं?",
        ],
    ),
    Scene(
        "NUM_PLACE_VALUE_BUNDLES",
        "priya",
        "प्रिया हर बंडल को एक गिनती है, दस नहीं",
        [
            "प्रिया, तुमने कैसे गिना? धीरे से बताओ।",
            "देखो, हर बंडल में कितनी तीलियाँ हैं? मेरे साथ गिनो: 10, 20, 30, 40।",
            "तुमने 11 कहा था, गिनने पर कितना आया? कौन-सा ठीक है?",
            "अब ये करो: 6 बंडल और 2 खुली तीलियाँ।",
        ],
    ),
    Scene(
        "NUM_PLACE_VALUE_BUNDLES",
        "aman",
        "अमन चालीस सुनकर 40 लिखता है और उसके आगे 7 लिख देता है",
        [
            "अमन, तुमने 407 कैसे लिखा? बताओ।",
            "आओ गिनते हैं: 4 बंडल यानी 10, 20, 30, 40, फिर 7 खुली तीलियाँ। मिलाकर कितनी हुईं?",
            "तुमने 407 कहा, गिनकर कुछ और आया। कौन-सा सही है और क्यों?",
            "अब खुद करो: 3 बंडल और 5 तीलियाँ।",
        ],
    ),
    Scene(
        "NUM_SUB_REGROUP_BUNDLES",
        "ravi",
        "रवि ने छोटी संख्या में से बड़ी घटा दी",
        [
            "रवि, सही उत्तर 16 है, इसे याद कर लो।",  # tell the answer: must not teach
            "रवि, तुमने कैसे किया?",
            "बंडल खोलकर गिनो, कितनी खुली तीलियाँ हुईं?",
            "अब नया सवाल: 61 में से 28।",
            "और ये भी करो: 74 में से 39।",
        ],
        label="tell-answer relapse",
    ),
]


class RoleLog(logging.Handler):
    """Collects `llm_role role=... fallback_used=...` INFO lines from the real pipeline."""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.calls: list[tuple[str, bool]] = []
        self._pattern = re.compile(r"llm_role role=(\w+) .* fallback_used=(true|false)")

    def emit(self, record: logging.LogRecord) -> None:
        m = self._pattern.search(record.getMessage())
        if m:
            self.calls.append((m.group(1), m.group(2) == "true"))


@dataclass
class Spend:
    per_model: dict[str, list[int]] = field(default_factory=lambda: defaultdict(lambda: [0, 0]))

    def add(self, model: str, input_tokens: int, output_tokens: int, cache_read: int) -> None:
        self.per_model[model][0] += input_tokens
        self.per_model[model][1] += output_tokens
        _ = cache_read

    def usd(self) -> float:
        total = 0.0
        for model, (tin, tout) in self.per_model.items():
            if "sonnet" in model:
                total += tin / 1e6 * settings.SONNET_INPUT_USD_PER_MTOK
                total += tout / 1e6 * settings.SONNET_OUTPUT_USD_PER_MTOK
            else:
                total += tin / 1e6 * settings.HAIKU_INPUT_USD_PER_MTOK
                total += tout / 1e6 * settings.HAIKU_OUTPUT_USD_PER_MTOK
        return total


async def run(max_usd: float) -> tuple[str, int]:
    if not settings.ANTHROPIC_API_KEY or settings.LLM_PROVIDER == "mock":
        print("ANTHROPIC_API_KEY not set (or LLM_PROVIDER=mock): nothing to run.")
        return "", 1

    spend = Spend()
    real_log = llm_client.log_llm_call

    async def metered(**kwargs: object) -> None:
        spend.add(
            str(kwargs.get("model", "")),
            int(kwargs.get("input_tokens", 0) or 0),  # type: ignore[call-overload]
            int(kwargs.get("output_tokens", 0) or 0),  # type: ignore[call-overload]
            int(kwargs.get("cache_read_tokens", 0) or 0),  # type: ignore[call-overload]
        )
        await real_log(**kwargs)  # type: ignore[arg-type]

    llm_client.log_llm_call = metered  # type: ignore[assignment]
    settings.LLM_CALL_LOG_ENABLED = False

    role_log = RoleLog()
    logging.getLogger("abhyas.llm.client").addHandler(role_log)
    logging.getLogger("abhyas.llm.client").setLevel(logging.INFO)

    lines_out: list[str] = []
    word_cap_violations: list[str] = []
    leaks: list[str] = []
    turn_counts: list[int] = []
    verdicts: Counter[str] = Counter()
    end_reasons: Counter[str] = Counter()

    store = InMemorySceneStore()
    runner = SceneRunner(store=store)

    for n, sc in enumerate(SCENES, 1):
        if spend.usd() > max_usd * 0.92:
            lines_out.append(
                f"\n## Scene {n}: SKIPPED (spend cap {max_usd:.2f} USD nearly reached)\n"
            )
            continue
        move = load_move_card(sc.move_id)
        teacher = uuid.uuid4()
        record = await runner.create_scene(teacher, sc.move_id, one_on_one_persona=sc.child)
        true_mid = record.scene_state.children[0].misconception
        diag: DiagnosisResult = await diagnose(sc.diagnosis, move, true_mid)
        verdicts[diag.verdict.value] += 1
        title = f"{sc.move_id} / {sc.child}" + (f" / {sc.label}" if sc.label else "")
        lines_out.append(f"\n## Scene {n}: {title}\n")
        lines_out.append(
            f"- diagnosis text: {sc.diagnosis!r} -> **{diag.verdict.value}** "
            f"({diag.reason}, matched={diag.matched_misconception}, classifier={diag.used_classifier})"
        )
        states: list[str] = []
        turns_done = 0
        for teacher_line in sc.turns:
            result = await runner.turn(record.scene_id, teacher_line, synthesize_audio=False)
            turns_done += 1
            scene_now = await store.get(record.scene_id)
            assert scene_now is not None
            child = scene_now.scene_state.children[0]
            states.append(child.state.name)
            tr = result.turn
            lines_out.append(f"- T{turns_done} teacher: {teacher_line}")
            lines_out.append(f"  - acts tagged: {tr.acts}  -> child state **{child.state.name}**")
            for resp, line in zip(tr.child_responses, tr.child_lines, strict=False):
                text = line.line_hi
                words = len(text.split())
                cap = child_line_word_cap(resp.kind)
                flag = ""
                if words > cap and resp.kind != ResponseKind.SILENT:
                    word_cap_violations.append(f"scene {n} T{turns_done}: {words}>{cap}: {text}")
                    flag = f"  **OVER CAP {words}>{cap}**"
                if find_placeholder_leak(text):
                    leaks.append(f"scene {n} T{turns_done}: {text}")
                    flag += "  **PLACEHOLDER LEAK**"
                lines_out.append(
                    f"  - {resp.persona_id} [{resp.kind.value}, answer={resp.answer}] ({words} words): "
                    f"{text}{flag}"
                )
            if tr.ended:
                end_reasons[tr.end_reason or "?"] += 1
                break
        turn_counts.append(turns_done)
        lines_out.append(f"- states by turn: {states}; turns: {turns_done}")

        # coach on the one-on-one rubric, as the service does after a scene
        scene_final = await store.get(record.scene_id)
        assert scene_final is not None
        all_turns: list[SceneTurn] = []
        acts_per_turn: list[list[TeachingAct]] = []
        for t in scene_final.turns:
            all_turns.append(SceneTurn(speaker="teacher", text_hi=t.transcript))
            acts_per_turn.append(
                [TeachingAct(a) for a in t.acts if a in TeachingAct._value2member_map_]
            )
            for cl in t.child_lines:
                if cl.line_hi:
                    all_turns.append(SceneTurn(speaker=cl.persona_id, text_hi=cl.line_hi))
        child_state = scene_final.scene_state.children[0]
        trajectory = [ChildState.MISCONCEPTION, *[h[1] for h in child_state.history]]
        coach_move = move.one_on_one_view()
        answer = scene_final.scene_state.current_item.answer()
        try:
            res = await coach_feedback(
                move=coach_move,
                turns=all_turns,
                acts=acts_per_turn,
                trajectories={sc.child: trajectory},
                target_child_id=sc.child,
                current_item_answer=answer,
                diagnosis=diag,
                one_on_one=True,
            )
            fb, used_fb = res.feedback, res.used_fallback
        except Exception as exc:  # report, do not hide
            lines_out.append(f"- coach raised {type(exc).__name__}: {exc}")
            fb = fallback_coach_feedback(
                coach_move,
                all_turns,
                acts_per_turn,
                {sc.child: trajectory},
                sc.child,
                answer,
                diagnosis=diag,
                one_on_one=True,
                reason="live_script_error",
            )
            used_fb = True
        lines_out.append(f"- coach (fallback_used={used_fb}): scores={fb.scores}")
        lines_out.append(f"  - strength: {fb.strength_hi}")
        lines_out.append(f"  - change: {fb.change_hi}")
        lines_out.append(f"  - exact words: {fb.exact_words_hi}")

    by_role: dict[str, list[bool]] = defaultdict(list)
    for role, used in role_log.calls:
        by_role[role].append(used)

    summary = ["# One-on-one live run (real models)\n"]
    summary.append(
        f"- scenes run: {len(turn_counts)} of {len(SCENES)}; turns per scene: {turn_counts}"
    )
    summary.append(f"- end reasons: {dict(end_reasons)}; diagnosis verdicts: {dict(verdicts)}")
    summary.append("- fallback_used by role (calls, fallback count, rate):")
    for role, flags in sorted(by_role.items()):
        summary.append(
            f"  - {role}: {len(flags)} calls, {sum(flags)} fallbacks, {sum(flags) / len(flags):.0%}"
        )
    summary.append(f"- word-cap violations: {len(word_cap_violations)}")
    summary.extend(f"  - {v}" for v in word_cap_violations)
    summary.append(f"- placeholder leaks: {len(leaks)}")
    summary.extend(f"  - {v}" for v in leaks)
    models = {m: tuple(v) for m, v in spend.per_model.items()}
    summary.append(f"- tokens by model (in, out): {models}; estimated spend: US${spend.usd():.3f}")
    return "\n".join(summary) + "\n" + "\n".join(lines_out) + "\n", 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-usd", type=float, default=1.0)
    parser.add_argument("--out", default=str(ROOT / "eval" / "one_on_one" / "LIVE_REPORT.md"))
    args = parser.parse_args()
    report, code = asyncio.run(run(args.max_usd))
    if code == 0:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        head = report.split("\n## Scene", 1)[0]
        sys.stdout.buffer.write(head.encode("utf-8"))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
