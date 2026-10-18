"""Cost report generator for Abhyas (spec/11, T61).

Reads llm_call and speech_spend rows from DATABASE_URL.
Computes:
- Total LLM cost and Speech spend
- Cost per teacher
- Cost per completed weekly loop (SessionState DONE)
- Cost per day

Writes formatted eval/cost/REPORT.md.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.config import settings
from backend.app.db.models import LLMCall, SessionState, SpeechSpend, Teacher

REPORT_PATH = Path(__file__).resolve().parent / "REPORT.md"


@dataclass
class CostMetrics:
    environment_label: str
    date_start: date | None
    date_end: date | None
    n_teachers: int
    n_completed_loops: int
    n_llm_calls: int
    n_speech_records: int
    llm_tokens_input: int
    llm_tokens_output: int
    llm_tokens_cache_read: int
    llm_cost_usd: float
    llm_cost_inr: float
    speech_cost_inr: float
    total_cost_inr: float
    cost_per_teacher_inr: float
    cost_per_completed_loop_inr: float
    daily_spend: list[dict[str, Any]] = field(default_factory=list)
    model_breakdown: list[dict[str, Any]] = field(default_factory=list)
    speech_breakdown: list[dict[str, Any]] = field(default_factory=list)


def compute_llm_call_cost_usd(
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
) -> float:
    """Computes call cost in USD according to Claude pricing tunables in settings."""
    m = (model or "").lower()
    if "haiku" in m:
        rate_input = settings.HAIKU_INPUT_USD_PER_MTOK
        rate_output = settings.HAIKU_OUTPUT_USD_PER_MTOK
        rate_cache = settings.HAIKU_CACHE_READ_USD_PER_MTOK
    else:
        # Sonnet or default smart/build
        rate_input = settings.SONNET_INPUT_USD_PER_MTOK
        rate_output = settings.SONNET_OUTPUT_USD_PER_MTOK
        rate_cache = settings.SONNET_CACHE_READ_USD_PER_MTOK

    cost_usd = (
        (input_tokens / 1_000_000.0) * rate_input
        + (output_tokens / 1_000_000.0) * rate_output
        + (cache_read_tokens / 1_000_000.0) * rate_cache
    )
    return cost_usd


async def generate_cost_metrics(
    session: AsyncSession,
    include_mock: bool = False,
    force_env_label: str | None = None,
) -> CostMetrics:
    """Queries DB session and computes comprehensive cost metrics."""
    # 1. Teachers count
    teacher_stmt = select(func.count(Teacher.id))
    n_teachers = (await session.scalar(teacher_stmt)) or 0

    # 2. Completed loops count (SessionState.state == 'DONE')
    done_stmt = select(func.count(SessionState.teacher_id)).where(SessionState.state == "DONE")
    n_completed_loops = (await session.scalar(done_stmt)) or 0

    # 3. LLM Calls
    llm_stmt = select(LLMCall).order_by(LLMCall.created_at.asc())
    llm_rows = list((await session.scalars(llm_stmt)).all())

    # 4. Speech Spend
    speech_stmt = select(SpeechSpend).order_by(SpeechSpend.at.asc())
    speech_rows = list((await session.scalars(speech_stmt)).all())

    # Determine environment label
    has_mock_llm = any(
        (row.model or "").lower() == "mock" or (row.role or "").lower() == "mock"
        for row in llm_rows
    )
    has_mock_speech = any(row.provider.lower() == "mock" for row in speech_rows)

    if force_env_label:
        env_label = force_env_label
    elif has_mock_llm or has_mock_speech or settings.ENVIRONMENT != "production":
        env_label = "local/mock"
    else:
        env_label = "hosted"

    # Filter mock if not included
    filtered_llm = [
        row
        for row in llm_rows
        if include_mock or ((row.model or "").lower() != "mock" and (row.role or "") != "mock")
    ]
    filtered_speech = [row for row in speech_rows if include_mock or row.provider.lower() != "mock"]

    # Date range
    all_dates: list[date] = []
    for r in filtered_llm:
        if r.created_at:
            all_dates.append(r.created_at.date())
    for s in filtered_speech:
        if s.at:
            all_dates.append(s.at.date())

    date_start = min(all_dates) if all_dates else None
    date_end = max(all_dates) if all_dates else None

    # LLM Breakdown
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_tokens = 0
    total_llm_usd = 0.0

    model_groups: dict[str, dict[str, Any]] = {}
    daily_groups: dict[date, dict[str, float]] = {}

    for row in filtered_llm:
        model_name = row.model or "unknown"
        inp = row.input_tokens or 0
        out = row.output_tokens or 0
        cache = row.cache_read_tokens or 0
        call_cost_usd = compute_llm_call_cost_usd(model_name, inp, out, cache)
        call_cost_inr = call_cost_usd * settings.USD_TO_INR

        total_input_tokens += inp
        total_output_tokens += out
        total_cache_tokens += cache
        total_llm_usd += call_cost_usd

        if model_name not in model_groups:
            model_groups[model_name] = {
                "model": model_name,
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cost_usd": 0.0,
                "cost_inr": 0.0,
            }
        model_groups[model_name]["calls"] += 1
        model_groups[model_name]["input_tokens"] += inp
        model_groups[model_name]["output_tokens"] += out
        model_groups[model_name]["cache_read_tokens"] += cache
        model_groups[model_name]["cost_usd"] += call_cost_usd
        model_groups[model_name]["cost_inr"] += call_cost_inr

        if row.created_at:
            d = row.created_at.date()
            if d not in daily_groups:
                daily_groups[d] = {"llm_inr": 0.0, "speech_inr": 0.0}
            daily_groups[d]["llm_inr"] += call_cost_inr

    total_llm_inr = total_llm_usd * settings.USD_TO_INR

    # Speech Breakdown
    total_speech_inr = 0.0
    speech_groups: dict[str, dict[str, Any]] = {}

    for row in filtered_speech:
        key = f"{row.provider}:{row.kind}"
        total_speech_inr += row.cost_inr
        if key not in speech_groups:
            speech_groups[key] = {
                "provider": row.provider,
                "kind": row.kind,
                "count": 0,
                "units": 0,
                "cost_inr": 0.0,
            }
        speech_groups[key]["count"] += 1
        speech_groups[key]["units"] += row.units
        speech_groups[key]["cost_inr"] += row.cost_inr

        if row.at:
            d = row.at.date()
            if d not in daily_groups:
                daily_groups[d] = {"llm_inr": 0.0, "speech_inr": 0.0}
            daily_groups[d]["speech_inr"] += row.cost_inr

    total_cost_inr = total_llm_inr + total_speech_inr

    cost_per_teacher = (total_cost_inr / n_teachers) if n_teachers > 0 else 0.0
    cost_per_loop = (total_cost_inr / n_completed_loops) if n_completed_loops > 0 else 0.0

    daily_spend = [
        {
            "date": d.isoformat(),
            "llm_inr": round(daily_groups[d]["llm_inr"], 2),
            "speech_inr": round(daily_groups[d]["speech_inr"], 2),
            "total_inr": round(daily_groups[d]["llm_inr"] + daily_groups[d]["speech_inr"], 2),
        }
        for d in sorted(daily_groups.keys())
    ]

    return CostMetrics(
        environment_label=env_label,
        date_start=date_start,
        date_end=date_end,
        n_teachers=n_teachers,
        n_completed_loops=n_completed_loops,
        n_llm_calls=len(filtered_llm),
        n_speech_records=len(filtered_speech),
        llm_tokens_input=total_input_tokens,
        llm_tokens_output=total_output_tokens,
        llm_tokens_cache_read=total_cache_tokens,
        llm_cost_usd=round(total_llm_usd, 4),
        llm_cost_inr=round(total_llm_inr, 2),
        speech_cost_inr=round(total_speech_inr, 2),
        total_cost_inr=round(total_cost_inr, 2),
        cost_per_teacher_inr=round(cost_per_teacher, 2),
        cost_per_completed_loop_inr=round(cost_per_loop, 2),
        daily_spend=daily_spend,
        model_breakdown=list(model_groups.values()),
        speech_breakdown=list(speech_groups.values()),
    )


def format_markdown_report(metrics: CostMetrics) -> str:
    """Renders CostMetrics to a clean, transparent Markdown document."""
    date_range_str = (
        f"{metrics.date_start} to {metrics.date_end}"
        if metrics.date_start and metrics.date_end
        else "None recorded"
    )

    lines: list[str] = [
        f"# Abhyas Cost Report ({metrics.environment_label})",
        "",
        f"- **Environment**: `{metrics.environment_label}`",
        f"- **Report Generated**: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"- **Date Range**: {date_range_str}",
        f"- **Sample Size**: {metrics.n_teachers} teachers, {metrics.n_completed_loops} completed weekly loops, "
        f"{metrics.n_llm_calls} LLM calls, {metrics.n_speech_records} speech records",
        "",
        "---",
        "",
        "## 1. Executive Cost Summary",
        "",
        "| Metric | Computed Value |",
        "|---|---|",
        f"| **Total Spend** | **₹{metrics.total_cost_inr:,.2f}** |",
        f"| Total LLM Cost | ₹{metrics.llm_cost_inr:,.2f} (${metrics.llm_cost_usd:,.4f}) |",
        f"| Total Speech Cost | ₹{metrics.speech_cost_inr:,.2f} |",
        f"| **Cost per Teacher** | **₹{metrics.cost_per_teacher_inr:,.2f}** |",
        f"| **Cost per Completed Weekly Loop (DONE)** | **₹{metrics.cost_per_completed_loop_inr:,.2f}** |",
        "",
        "---",
        "",
        "## 2. LLM Call Breakdown",
        "",
        "| Model | Calls | Input Tokens | Output Tokens | Cache Read Tokens | Cost (USD) | Cost (INR) |",
        "|---|---|---|---|---|---|---|",
    ]

    if metrics.model_breakdown:
        for m in metrics.model_breakdown:
            lines.append(
                f"| `{m['model']}` | {m['calls']} | {m['input_tokens']:,} | {m['output_tokens']:,} | "
                f"{m['cache_read_tokens']:,} | ${m['cost_usd']:.4f} | ₹{m['cost_inr']:.2f} |"
            )
    else:
        lines.append("| None | 0 | 0 | 0 | 0 | $0.0000 | ₹0.00 |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 3. Speech Spend Breakdown",
            "",
            "| Provider | Kind | Records | Units (Sec / Chars) | Cost (INR) |",
            "|---|---|---|---|---|",
        ]
    )

    if metrics.speech_breakdown:
        for s in metrics.speech_breakdown:
            lines.append(
                f"| `{s['provider']}` | `{s['kind']}` | {s['count']} | {s['units']:,} | ₹{s['cost_inr']:.2f} |"
            )
    else:
        lines.append("| None | - | 0 | 0 | ₹0.00 |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 4. Daily Spend Summary",
            "",
            "| Date | LLM Cost (INR) | Speech Cost (INR) | Daily Total (INR) |",
            "|---|---|---|---|",
        ]
    )

    if metrics.daily_spend:
        for d in metrics.daily_spend:
            lines.append(
                f"| {d['date']} | ₹{d['llm_inr']:.2f} | ₹{d['speech_inr']:.2f} | ₹{d['total_inr']:.2f} |"
            )
    else:
        lines.append("| None | ₹0.00 | ₹0.00 | ₹0.00 |")

    lines.extend(
        [
            "",
            "---",
            "",
            "## 5. Pricing Rates & Methodology",
            "",
            "- **Claude Haiku 5.5**: $0.10 input / $0.50 output / $0.01 cache read per MTok (prompts up to 100k).  ",
            "  *Source*: [Anthropic Claude Pricing](https://platform.claude.com/docs/en/about-claude/pricing) (as-of 2026-10).",
            "- **Claude Sonnet 5.5**: $2.00 input / $10.00 output / $0.10 cache read per MTok.  ",
            "  *Source*: [Anthropic Claude Pricing](https://platform.claude.com/docs/en/about-claude/pricing) (as-of 2026-10).",
            "- **Sarvam Saaras STT**: ₹30.00 per hour (₹0.50 per minute).  ",
            "  *Source*: [Sarvam AI Pricing](https://docs.sarvam.ai/api-reference-docs/pricing) (as-of 2026-10).",
            "- **Sarvam Bulbul v3 TTS**: ₹30.00 per 10,000 characters (₹3.00 per 1,000 characters).  ",
            "  *Source*: [Sarvam AI Pricing](https://docs.sarvam.ai/api-reference-docs/pricing) (as-of 2026-10).",
            f"- **USD to INR Exchange Rate**: ₹{settings.USD_TO_INR:.2f} (*assumption, update before submission*).",
            "- **Policy**: No uncomputed numbers. Mock provider rows are excluded unless explicitly requested and labelled as mock.",
            "",
        ]
    )

    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate cost evaluation report from database.")
    parser.add_argument(
        "--db-url",
        default=None,
        help="Database URL (default: settings.DATABASE_URL normalized to asyncpg)",
    )
    parser.add_argument(
        "--output",
        default=str(REPORT_PATH),
        help=f"Output markdown file path (default: {REPORT_PATH})",
    )
    parser.add_argument(
        "--include-mock",
        action="store_true",
        help="Include mock provider records in computation (labels report as mock)",
    )
    args = parser.parse_args()

    raw_url = args.db_url or settings.DATABASE_URL
    if raw_url.startswith("postgresql://"):
        raw_url = raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    metrics: CostMetrics
    try:
        engine = create_async_engine(
            raw_url, connect_args={"timeout": 5} if "postgresql" in raw_url else {}
        )
        async_session = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with async_session() as session:
                metrics = await generate_cost_metrics(session, include_mock=args.include_mock)
        finally:
            await engine.dispose()
    except Exception as exc:  # Rule C: In local dev/mock mode without live PostgreSQL running, fallback to empty local/mock metrics
        print(f"Notice: Could not query database ({exc}); generating empty local/mock report.")
        metrics = CostMetrics(
            environment_label="local/mock",
            date_start=None,
            date_end=None,
            n_teachers=0,
            n_completed_loops=0,
            n_llm_calls=0,
            n_speech_records=0,
            llm_tokens_input=0,
            llm_tokens_output=0,
            llm_tokens_cache_read=0,
            llm_cost_usd=0.0,
            llm_cost_inr=0.0,
            speech_cost_inr=0.0,
            total_cost_inr=0.0,
            cost_per_teacher_inr=0.0,
            cost_per_completed_loop_inr=0.0,
        )

    content = format_markdown_report(metrics)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    print(f"Cost report written to {out_path} ({metrics.environment_label})")
    print(
        f"Total: INR {metrics.total_cost_inr:.2f} | Per teacher: INR {metrics.cost_per_teacher_inr:.2f} | Per loop: INR {metrics.cost_per_completed_loop_inr:.2f}"
    )


if __name__ == "__main__":
    asyncio.run(main())
