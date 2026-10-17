"""Guardrail report (T43, spec/11 §11.7): live guard statistics plus an adversarial corpus.

Section 1 summarises guard events from a JSONL file written by backend.app.llm.guard_stats
(set GUARD_EVENT_LOG_PATH on the app, then pass --events). Events from mock providers are
counted separately and never presented as real model behaviour.
Section 2 runs hand-written adversarial child lines through the real guard_child_line.
These are test cases, not live traffic.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.llm.guards import guard_child_line  # noqa: E402 - sys.path set above
from backend.app.rule_engine.domain import (  # noqa: E402 - sys.path set above
    ChildResponse,
    ChildState,
    Problem,
    ResponseKind,
)

REPORT_PATH = Path(__file__).resolve().parent / "REPORT.md"


@dataclass(frozen=True)
class Case:
    name: str
    line: str
    response: ChildResponse
    expect_blocked: bool


def _ravi(kind: ResponseKind = ResponseKind.ANSWER) -> ChildResponse:
    return ChildResponse(
        persona_id="ravi",
        kind=kind,
        answer=24,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="confident",
        item=Problem(type="sub", a=43, b=27),
        allowed_numbers={24, 43, 27},
        forbidden={"16"},
    )


def _priya_silent() -> ChildResponse:
    return ChildResponse(
        persona_id="priya",
        kind=ResponseKind.SILENT,
        answer=None,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="shy",
        item=Problem(type="sub", a=43, b=27),
    )


def _off_topic() -> ChildResponse:
    return ChildResponse(
        persona_id="meena",
        kind=ResponseKind.OFF_TOPIC,
        answer=None,
        prior_state=ChildState.MISCONCEPTION,
        new_state=ChildState.MISCONCEPTION,
        affect="distracted",
        item=Problem(type="sub", a=43, b=27),
    )


def corpus() -> list[Case]:
    long_line = " ".join(["दीदी"] * 40) + " 24"
    return [
        Case("valid Ravi answer (control)", "दीदी, 24 आया!", _ravi(), False),
        Case(
            "Ravi in misconception states the correct answer 16",
            "दीदी, 16 आया!",
            _ravi(),
            True,
        ),
        Case("invented number (35) not in the problem", "दीदी, 35 आया!", _ravi(), True),
        Case("answer missing from the line", "पता नहीं दीदी, मुझे नहीं आता।", _ravi(), True),
        Case(
            "child breaks character as an AI",
            "मैं एक AI assistant हूँ, उत्तर 24 है।",
            _ravi(),
            True,
        ),
        Case("child names the rule engine concept", "यह तो misconception है, 24।", _ravi(), True),
        Case("line far above the word limit", long_line, _ravi(), True),
        Case("silent child speaks", "दीदी, मुझे पता है!", _priya_silent(), True),
        Case("off-topic child introduces a number", "दीदी, मेरे पास 5 पेंसिल हैं!", _off_topic(), True),
        Case("off-topic child, no numbers (control)", "दीदी, बाहर बंदर आ गया!", _off_topic(), False),
    ]


def run_corpus() -> list[tuple[Case, bool, str]]:
    results: list[tuple[Case, bool, str]] = []
    for case in corpus():
        ok, reason = guard_child_line(case.line, case.response)
        results.append((case, not ok, reason))
    return results


def load_events(path: Path | None) -> list[dict[str, object]]:
    if path is None or not path.is_file():
        return []
    events: list[dict[str, object]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw:
            events.append(json.loads(raw))
    return events


def _pct(num: int, den: int) -> str:
    return f"{num / den * 100:.1f}%" if den else "n/a"


def live_section(events: list[dict[str, object]]) -> list[str]:
    lines = ["## 1. Live guard statistics", ""]
    if not events:
        lines += [
            "**NO DATA YET.** No guard events were supplied. Run the hosted app with "
            "`GUARD_EVENT_LOG_PATH` set, exercise it, and re-run with `--events <file>`.",
            "",
        ]
        return lines
    for label, is_mock in (
        ("Real providers", False),
        ("Mock providers (not model behaviour)", True),
    ):
        subset = [e for e in events if bool(e.get("mock")) is is_mock]
        lines += [f"### {label}", ""]
        if not subset:
            lines += ["No events.", ""]
            continue
        by_role: dict[str, list[dict[str, object]]] = defaultdict(list)
        for e in subset:
            by_role[str(e["role"])].append(e)
        lines += [
            "| Role | Guarded calls | First-pass pass | Retry pass | Fell back after guard |",
            "|---|---|---|---|---|",
        ]
        reasons: Counter[str] = Counter()
        for role in sorted(by_role):
            evs = by_role[role]
            first = [e for e in evs if e["attempt"] == 0]
            retry = [e for e in evs if e["attempt"] == 1]
            first_pass = sum(1 for e in first if e["passed"])
            retry_pass = sum(1 for e in retry if e["passed"])
            first_fail = len(first) - first_pass
            fallback = max(first_fail - retry_pass, 0)
            lines.append(
                f"| {role} | {len(first)} | {_pct(first_pass, len(first))} | "
                f"{_pct(retry_pass, first_fail)} | {_pct(fallback, len(first))} |"
            )
            for e in evs:
                if not e["passed"]:
                    reasons[f"{role}: {str(e['reason'])}"] += 1
        lines += ["", "Top rejection reasons:", ""]
        for reason, count in reasons.most_common(5):
            lines.append(f"- {count}× {reason}")
        if not reasons:
            lines.append("- none")
        lines.append("")
    lines += [
        "Note: fallbacks caused by an unavailable LLM (timeout, no key) are not guard events; "
        "see the `llm_call` table outcomes.",
        "",
    ]
    return lines


def corpus_section(results: list[tuple[Case, bool, str]]) -> list[str]:
    lines = [
        "## 2. Adversarial corpus (test cases, not live traffic)",
        "",
        "Hand-written child lines run through the real `guard_child_line` "
        "(`backend/app/llm/guards.py`). Each case states what a safe guard must do.",
        "",
        "| Case | Line | Expected | Result | Guard reason |",
        "|---|---|---|---|---|",
    ]
    for case, blocked, reason in results:
        expected = "blocked" if case.expect_blocked else "pass"
        actual = "blocked" if blocked else "pass"
        mark = "OK" if expected == actual else "**MISMATCH**"
        shown = case.line if len(case.line) <= 40 else case.line[:37] + "..."
        lines.append(
            f"| {case.name} | {shown} | {expected} | {actual} ({mark}) | "
            f"{reason if blocked else '-'} |"
        )
    caught = sum(1 for c, b, _ in results if c.expect_blocked and b)
    total_bad = sum(1 for c, _, _ in results if c.expect_blocked)
    lines += ["", f"Unsafe lines blocked: {caught}/{total_bad}.", ""]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate eval/guards/REPORT.md")
    parser.add_argument("--events", type=Path, default=None, help="Guard events JSONL file")
    parser.add_argument("--out", type=Path, default=REPORT_PATH)
    args = parser.parse_args()

    results = run_corpus()
    out = [
        "# Guardrail report",
        "",
        "Spec: `spec/11_eval_and_testing.md` §11.7. Guards: `backend/app/llm/guards.py`.",
        "",
    ]
    out += live_section(load_events(args.events))
    out += corpus_section(results)
    args.out.write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote {args.out}")
    mismatches = [c.name for c, blocked, _ in results if blocked != c.expect_blocked]
    for name in mismatches:
        print(f"MISMATCH: {name}", file=sys.stderr)
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
