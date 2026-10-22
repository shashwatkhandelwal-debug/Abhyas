"""Claude LLM Client wrapper interface and tool-forced caller (spec/05 §5.1).

Implements Anthropic Messages API calling, prompt caching, call logging,
daily token budget guard (spec/12 §12.8), and deterministic MockLLM.
"""

from __future__ import annotations

import contextvars
import functools
import hashlib
import inspect
import json
import logging
import time
import zoneinfo
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

import anthropic
from anthropic import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from anthropic.resources.messages import AsyncMessages
from sqlalchemy import func, select

from backend.app.config import settings
from backend.app.db.models import LLMCall
from backend.app.db.session import async_session_factory

logger = logging.getLogger("abhyas.llm.client")

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


def get_start_of_day_ist_utc() -> datetime:
    """Returns the start of current day in IST (Asia/Kolkata) as a UTC datetime."""
    now_ist = datetime.now(IST)
    start_of_day_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_of_day_ist.astimezone(UTC)


async def get_daily_token_usage_db() -> int | None:
    """Queries total tokens used today in IST from llm_call table (CHANGES 254f622 Item 1)."""
    try:
        start_utc = get_start_of_day_ist_utc()
        async with async_session_factory() as session:
            stmt = select(
                func.coalesce(
                    func.sum(
                        func.coalesce(LLMCall.input_tokens, 0)
                        + func.coalesce(LLMCall.output_tokens, 0)
                        + func.coalesce(LLMCall.cache_read_tokens, 0)
                    ),
                    0,
                )
            ).where(LLMCall.created_at >= start_utc)
            result = await session.execute(stmt)
            val = result.scalar_one_or_none()
            return int(val) if val is not None else 0
    except Exception as exc:
        logger.debug("Failed querying daily token usage from DB: %s", exc)
        return None


class LLMUnavailable(Exception):
    """Raised when LLM call fails after retries or service is unavailable (spec/05 §5.1)."""

    pass


class ModelConfigurationError(RuntimeError):
    """Raised when a configured Claude model ID is invalid or rejected by Anthropic (spec/05 §5.1)."""

    pass


class TokenBudgetExceeded(LLMUnavailable):
    """Raised when the daily token budget has been exceeded (spec/12 §12.8)."""

    pass


class TokenBudgetTracker:
    """In-memory and DB-backed tracker for daily token budget in IST (spec/12 §12.8, CHANGES 254f622 Item 1)."""

    def __init__(self, daily_budget: int | None = None) -> None:
        self.daily_budget: int = daily_budget or settings.LLM_DAILY_TOKEN_BUDGET
        self._current_date: str = datetime.now(IST).strftime("%Y-%m-%d")
        self._tokens_used_today: int = 0

    def _check_and_reset_day(self) -> None:
        today = datetime.now(IST).strftime("%Y-%m-%d")
        if today != self._current_date:
            self._current_date = today
            self._tokens_used_today = 0

    async def sync_from_db(self) -> int:
        """Fetches total tokens consumed today in IST from DB and updates in-memory count."""
        self._check_and_reset_day()
        db_usage = await get_daily_token_usage_db()
        if db_usage is not None:
            self._tokens_used_today = db_usage
        return self._tokens_used_today

    def record_usage(
        self, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0
    ) -> None:
        """Records token consumption for the current day."""
        self._check_and_reset_day()
        self._tokens_used_today += input_tokens + output_tokens + cache_read_tokens

    def get_tokens_used_today(self) -> int:
        """Returns total tokens consumed today in IST."""
        self._check_and_reset_day()
        return self._tokens_used_today

    def is_exceeded(self) -> bool:
        """Returns True if today's token usage has reached or exceeded the budget."""
        self._check_and_reset_day()
        return self._tokens_used_today >= self.daily_budget

    def reset(self) -> None:
        """Resets the tracker counter for testing."""
        self._tokens_used_today = 0
        self._current_date = datetime.now(IST).strftime("%Y-%m-%d")


# Global singleton token budget tracker
budget_tracker = TokenBudgetTracker()

# Shared singleton AsyncAnthropic client
_anthropic_client: anthropic.AsyncAnthropic | None = None


def get_anthropic_client() -> anthropic.AsyncAnthropic:
    """Returns shared singleton AsyncAnthropic client."""
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=settings.LLM_TIMEOUT_SECONDS,
        )
    return _anthropic_client


async def close_anthropic_client() -> None:
    """Closes shared AsyncAnthropic client on shutdown."""
    global _anthropic_client
    if _anthropic_client is not None:
        await _anthropic_client.close()
        _anthropic_client = None


_role_fallback: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "abhyas_role_fallback", default=False
)
_R = TypeVar("_R")


def mark_fallback() -> None:
    """Called by a role's deterministic fallback so `logged_role` can report fallback_used."""
    _role_fallback.set(True)


def logged_role(
    role: str, model: Callable[[], str]
) -> Callable[[Callable[..., Awaitable[_R]]], Callable[..., Awaitable[_R]]]:
    """Decorator: one `llm_role` INFO line per role call (role, model, latency_ms, fallback_used).

    Fallback is read from the result's `used_fallback` field, or from `mark_fallback()`.
    """

    def wrap(fn: Callable[..., Awaitable[_R]]) -> Callable[..., Awaitable[_R]]:
        @functools.wraps(fn)
        async def inner(*args: Any, **kwargs: Any) -> _R:
            _role_fallback.set(False)
            started = time.perf_counter()
            result = await fn(*args, **kwargs)
            used = getattr(result, "used_fallback", None)
            log_role_call(
                role, model(), started, _role_fallback.get() if used is None else bool(used)
            )
            return result

        return inner

    return wrap


def log_role_call(role: str, model: str, started_at: float, fallback_used: bool) -> None:
    """One INFO line per role invocation (not per HTTP call): role, model, latency, fallback."""
    logger.info(
        "llm_role role=%s model=%s latency_ms=%d fallback_used=%s",
        role,
        model,
        int((time.perf_counter() - started_at) * 1000),
        str(fallback_used).lower(),
    )


# In-memory prompt cache
_PROMPT_CACHE: dict[str, str] = {}


def load_prompt(role: str, version: str = "v1") -> str:
    """Loads prompt template for given role and version string.

    Looks in backend/app/llm/prompts/{role}.{version}.md.
    Falls back to Python constants if markdown file is absent.
    """
    cache_key = f"{role}:{version}"
    if cache_key in _PROMPT_CACHE:
        return _PROMPT_CACHE[cache_key]

    prompt_dir = Path(__file__).parent / "prompts"
    prompt_file = prompt_dir / f"{role}.{version}.md"
    if prompt_file.is_file():
        text = prompt_file.read_text(encoding="utf-8")
        _PROMPT_CACHE[cache_key] = text
        return text

    # Try fallback to Python prompt modules
    try:
        import importlib

        mod = importlib.import_module(f"backend.app.llm.prompts.{role}")
        const_name = f"{role.upper()}_SYSTEM_PROMPT"
        if hasattr(mod, const_name):
            text = str(getattr(mod, const_name))
            _PROMPT_CACHE[cache_key] = text
            return text
    except (ImportError, AttributeError):
        pass

    logger.warning("Prompt not found for %s.%s, using empty prompt", role, version)
    return ""


async def log_llm_call(
    role: str,
    prompt_version: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    latency_ms: int,
    outcome: str,
) -> None:
    """Logs an LLM call row to the database (spec/05 §5.1)."""
    if not settings.LLM_CALL_LOG_ENABLED:
        return
    try:
        async with async_session_factory() as session:
            call_record = LLMCall(
                role=role,
                prompt_version=prompt_version,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                latency_ms=latency_ms,
                outcome=outcome,
            )
            session.add(call_record)
            await session.commit()
    except Exception as exc:
        # DB logging must never crash the application runtime
        logger.debug("Failed to record llm_call to database: %s", exc)


def _generate_schema_default(schema: dict[str, Any], role: str | None = None) -> dict[str, Any]:
    """Generates schema-valid default data for MockLLM."""
    # Role-specific tailored defaults that pass spec guards
    if role == "intent_router":
        return {"intent": "answer_for_step", "confidence": 0.95}
    if role == "act_tagger":
        return {
            "acts": ["ask_to_explain"],
            "addressed_child": "ravi",
            "problem": None,
            "quote": "रवि, 52 में से 17 कैसे घटाया? बताओ।",
        }
    if role == "child_voice":
        return {"line_hi": "पैंतालीस!"}
    if role == "coach":
        return {
            "scores": {"crit_explaining": 2},
            "evidence": {"crit_explaining": "रवि, 52 में से 17 कैसे घटाया? बताओ।"},
            "strength_hi": "आपने बच्चे से उसके सोचने का तरीका पूछा।",
            "change_hi": "अगली बार बच्चे को तीलियों से करके देखने को कहें।",
            "exact_words_hi": "बंडल और तीली लेकर देखो।",
            "improved_since_last": True,
            "confidence": 0.85,
        }
    if role == "fidelity_checker":
        return {
            "points": [{"id": "kp1", "status": "covered", "quote": "बंडल और तीली"}],
            "misconceptions": [],
            "confidence": 0.9,
        }
    if role == "question_classifier":
        return {
            "category": "pedagogy",
            "needs_clarification": False,
            "clarifying_question_hi": "",
            "search_query_hi": "घटाव",
            "confidence": 0.9,
        }
    if role == "translator":
        from backend.app.llm.schemas import MOCK_TRANSLATION_TEXT

        return {"text_en": MOCK_TRANSLATION_TEXT}
    if role == "guide_answerer":
        return {
            "answer_hi": "बच्चों को बंडल और तीलियों की मदद से दहाई-इकाई सिखाएं।",
            "source_ids": ["chunk-1"],
            "try_this_week_hi": "कक्षा में तीलियां इस्तेमाल करें।",
            "confidence": 0.9,
        }

    # Recursive generator for arbitrary JSON schema
    properties = schema.get("properties", {})
    result: dict[str, Any] = {}
    for key, prop in properties.items():
        prop_type = prop.get("type")
        if "enum" in prop and prop["enum"]:
            result[key] = prop["enum"][0]
        elif prop_type == "string":
            result[key] = prop.get("default", "")
        elif prop_type == "integer":
            result[key] = prop.get("default", 0)
        elif prop_type == "number":
            result[key] = prop.get("default", 0.0)
        elif prop_type == "boolean":
            result[key] = prop.get("default", False)
        elif prop_type == "array":
            result[key] = prop.get("default", [])
        elif prop_type == "object":
            result[key] = _generate_schema_default(prop)
        else:
            result[key] = None
    return result


class MockLLM:
    """Mock LLM returning golden outputs or schema defaults (spec/05 §5.1).

    Selected when ANTHROPIC_API_KEY is empty or LLM_PROVIDER=mock.
    The whole product runs end-to-end on MockLLM.
    """

    def __init__(self, golden_dir: Path | str | None = None) -> None:
        if golden_dir is None:
            self.golden_dir = Path(__file__).parents[2] / "tests" / "golden"
        else:
            self.golden_dir = Path(golden_dir)

    def _find_golden_output(
        self,
        role: str,
        messages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Looks for a golden fixture file matching the role and input."""
        role_dir = self.golden_dir / role
        if not role_dir.is_dir():
            return None

        # Try to find matching fixture (ignore negative test failure fixtures)
        files = [f for f in sorted(role_dir.glob("*.json")) if not f.stem.startswith("fail")]
        if not files:
            return None

        # If messages provided, compute hash
        msg_str = json.dumps(messages, sort_keys=True) if messages else ""
        content_hash = hashlib.sha256(msg_str.encode("utf-8")).hexdigest()[:8]

        # Check for direct hash match or inspect files
        for f in files:
            if content_hash in f.stem:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and "output" in data:
                        return data["output"]  # type: ignore
                    elif isinstance(data, dict):
                        return data
                except Exception:
                    continue

        # If no specific match, use the first fixture
        try:
            data = json.loads(files[0].read_text(encoding="utf-8"))
            if isinstance(data, dict) and "output" in data:
                return data["output"]  # type: ignore
            elif isinstance(data, dict):
                return data
        except Exception:
            return None

        return None

    async def call_tool(
        self,
        role: str,
        tool_name: str,
        input_schema: dict[str, Any],
        system: str = "",
        messages: list[dict[str, Any]] | None = None,
        prompt_version: str = "v1",
    ) -> dict[str, Any]:
        """Returns mock golden dictionary conforming to input_schema."""
        golden = self._find_golden_output(role, messages)
        if golden is not None:
            return golden

        return _generate_schema_default(input_schema, role=role)


_mock_llm_instance = MockLLM()


def get_mock_llm() -> MockLLM:
    """Returns singleton MockLLM instance."""
    return _mock_llm_instance


# Parameters accepted by the installed SDK's Messages.create(). Newer anthropic releases
# (1.13.0 and 2.0.0 checked) no longer accept `temperature`; passing it raises TypeError.
SDK_CREATE_PARAMS: frozenset[str] = frozenset(inspect.signature(AsyncMessages.create).parameters)


def build_create_kwargs(
    *,
    model: str,
    max_tokens: int,
    system_blocks: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    tool_choice: dict[str, Any],
    temperature: float | None = None,
    disable_thinking: bool = False,
) -> dict[str, Any]:
    """Builds Messages.create() kwargs; optional params are sent only if the SDK supports them."""
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_blocks,
        "messages": messages,
        "tools": tools,
        "tool_choice": tool_choice,
    }
    if temperature is not None and "temperature" in SDK_CREATE_PARAMS:
        kwargs["temperature"] = temperature
    if disable_thinking and "thinking" in SDK_CREATE_PARAMS:
        # With tool_choice=auto the model may spend the whole max_tokens budget thinking
        # (seen on claude-sonnet-5-5: stop_reason=max_tokens with an empty thinking block).
        # claude-sonnet-5-5 rejects {"type": "disabled"} and asks for "between_tools".
        kwargs["thinking"] = {"type": "between_tools"}
    return kwargs


# Models that answered 400 to a forced tool_choice; they get {"type": "auto"} from then on.
_MODELS_WITHOUT_FORCED_TOOL_CHOICE: set[str] = set()


def _is_forced_tool_choice_rejection(err: APIStatusError) -> bool:
    text = str(err).lower()
    return err.status_code == 400 and "tool_choice" in text and "not supported" in text


def _is_thinking_param_rejection(err: APIStatusError) -> bool:
    return err.status_code == 400 and "thinking" in str(err).lower()


def _with_tool_only_instruction(
    system_blocks: list[dict[str, Any]], tool_name: str
) -> list[dict[str, Any]]:
    """Appends the 'answer only by calling the tool' rule used when tool_choice is auto."""
    instruction = (
        f"IMPORTANT: Respond ONLY by calling the `{tool_name}` tool exactly once. "
        "Do not write any plain-text answer or any text before the tool call."
    )
    return [*system_blocks, {"type": "text", "text": instruction}]


async def call_tool(
    role: str,
    model: str,
    system: str,
    messages: list[dict[str, Any]],
    tool_name: str,
    input_schema: dict[str, Any],
    temperature: float = 0.0,
    max_tokens: int = 1024,
    timeout_s: float = 8.0,
    prompt_version: str = "v1",
) -> dict[str, Any]:
    """Spec 05 §5.1: Call Claude Messages API with forced tool use.

    Uses Anthropic Messages API with tools=[{name, description, input_schema}]
    and tool_choice={"type": "tool", "name": tool_name}; returns the tool input dict.
    """
    # 1. Check if mock provider is active
    if not settings.ANTHROPIC_API_KEY or settings.LLM_PROVIDER == "mock":
        t0 = time.perf_counter()
        result = await get_mock_llm().call_tool(
            role=role,
            tool_name=tool_name,
            input_schema=input_schema,
            system=system,
            messages=messages,
            prompt_version=prompt_version,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        await log_llm_call(
            role=role,
            prompt_version=prompt_version,
            model="mock",
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            latency_ms=latency_ms,
            outcome="mock_success",
        )
        return result

    # 2. Daily token budget guard (spec/12 §12.8, CHANGES 254f622 Item 1)
    await budget_tracker.sync_from_db()
    if budget_tracker.is_exceeded():
        logger.warning(
            "LLM daily token budget exceeded: %d >= %d",
            budget_tracker.get_tokens_used_today(),
            budget_tracker.daily_budget,
        )
        await log_llm_call(
            role=role,
            prompt_version=prompt_version,
            model=model,
            input_tokens=0,
            output_tokens=0,
            cache_read_tokens=0,
            latency_ms=0,
            outcome="budget_exceeded",
        )
        raise TokenBudgetExceeded(f"Daily token budget of {budget_tracker.daily_budget} exceeded")

    # 3. Setup Anthropic client and tool parameters
    client = get_anthropic_client()

    system_blocks: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    tools_spec: list[dict[str, Any]] = [
        {
            "name": tool_name,
            "description": f"Tool for role {role}",
            "input_schema": input_schema,
        }
    ]
    auto_tool_choice = model in _MODELS_WITHOUT_FORCED_TOOL_CHOICE
    tool_choice: dict[str, Any] = (
        {"type": "auto"} if auto_tool_choice else {"type": "tool", "name": tool_name}
    )
    token_ceiling = settings.LLM_MAX_TOKENS_CEILING
    if auto_tool_choice:
        system_blocks = _with_tool_only_instruction(system_blocks, tool_name)
        max_tokens += settings.LLM_AUTO_TOOL_CHOICE_TOKEN_HEADROOM
        token_ceiling += settings.LLM_AUTO_TOOL_CHOICE_TOKEN_HEADROOM

    send_thinking_param = True
    retries = 0
    max_retries = settings.LLM_MAX_RETRIES
    truncation_retried = False

    while True:
        t0 = time.perf_counter()
        try:
            create_kwargs = build_create_kwargs(
                model=model,
                max_tokens=max_tokens,
                system_blocks=system_blocks,
                messages=messages,
                tools=tools_spec,
                tool_choice=tool_choice,
                temperature=temperature,
                disable_thinking=auto_tool_choice and send_thinking_param,
            )
            response = await client.messages.create(**create_kwargs)
            latency_ms = int((time.perf_counter() - t0) * 1000)

            # Extract usage
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            cache_read_tokens = getattr(response.usage, "cache_read_input_tokens", 0) or 0

            # Record token usage
            budget_tracker.record_usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
            )

            # A reply cut off by max_tokens still carries a tool_use block, but its input is
            # the partial JSON parsed as {} -- never hand that to a role as if it were output.
            if getattr(response, "stop_reason", None) == "max_tokens":
                logger.warning(
                    "LLM reply truncated for role %s (model=%s, max_tokens=%d, output_tokens=%d)",
                    role,
                    model,
                    max_tokens,
                    output_tokens,
                )
                await log_llm_call(
                    role=role,
                    prompt_version=prompt_version,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cache_read_tokens=cache_read_tokens,
                    latency_ms=latency_ms,
                    outcome="truncated",
                )
                if not truncation_retried and max_tokens < token_ceiling:
                    truncation_retried = True
                    max_tokens = min(max_tokens * 2, token_ceiling)
                    continue
                raise LLMUnavailable(f"Anthropic reply truncated at max_tokens for {tool_name}")

            # Extract tool use output
            for content_block in response.content:
                if (
                    getattr(content_block, "type", None) == "tool_use"
                    and getattr(content_block, "name", None) == tool_name
                ):
                    raw_input = getattr(content_block, "input", {})
                    output_data: dict[str, Any] = raw_input if isinstance(raw_input, dict) else {}
                    await log_llm_call(
                        role=role,
                        prompt_version=prompt_version,
                        model=model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cache_read_tokens=cache_read_tokens,
                        latency_ms=latency_ms,
                        outcome="success",
                    )
                    return output_data

            # If tool_use was not found
            await log_llm_call(
                role=role,
                prompt_version=prompt_version,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cache_read_tokens=cache_read_tokens,
                latency_ms=latency_ms,
                outcome="no_tool_call",
            )
            raise LLMUnavailable(
                f"Anthropic response did not contain expected tool_use block for {tool_name}"
            )

        except (
            APITimeoutError,
            APIConnectionError,
            RateLimitError,
            InternalServerError,
        ) as err:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            if retries < max_retries:
                retries += 1
                logger.warning(
                    "LLM call retry %d/%d for role %s due to %s",
                    retries,
                    max_retries,
                    role,
                    err,
                )
                continue

            outcome = "timeout" if isinstance(err, APITimeoutError) else "failed"
            await log_llm_call(
                role=role,
                prompt_version=prompt_version,
                model=model,
                input_tokens=0,
                output_tokens=0,
                cache_read_tokens=0,
                latency_ms=latency_ms,
                outcome=outcome,
            )
            raise LLMUnavailable(f"LLM call failed after retries: {err}") from err

        except APIStatusError as err:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            if not auto_tool_choice and _is_forced_tool_choice_rejection(err):
                # Some models (e.g. claude-sonnet-5-5) reject {"type": "tool"}. Remember it and
                # retry once with "auto" plus an instruction to answer only via the tool.
                logger.warning(
                    "Model %s rejects forced tool_choice; using auto for role %s", model, role
                )
                _MODELS_WITHOUT_FORCED_TOOL_CHOICE.add(model)
                auto_tool_choice = True
                tool_choice = {"type": "auto"}
                system_blocks = _with_tool_only_instruction(system_blocks, tool_name)
                max_tokens += settings.LLM_AUTO_TOOL_CHOICE_TOKEN_HEADROOM
                token_ceiling += settings.LLM_AUTO_TOOL_CHOICE_TOKEN_HEADROOM
                continue
            if auto_tool_choice and send_thinking_param and _is_thinking_param_rejection(err):
                logger.warning("Model %s rejects the thinking param; retrying without it", model)
                send_thinking_param = False
                continue
            if err.status_code >= 500 and retries < max_retries:
                retries += 1
                logger.warning(
                    "LLM call 5xx retry %d/%d for role %s: %s",
                    retries,
                    max_retries,
                    role,
                    err,
                )
                continue

            await log_llm_call(
                role=role,
                prompt_version=prompt_version,
                model=model,
                input_tokens=0,
                output_tokens=0,
                cache_read_tokens=0,
                latency_ms=latency_ms,
                outcome="failed",
            )
            raise LLMUnavailable(f"Anthropic API error: {err}") from err


async def verify_configured_models(force: bool = False) -> dict[str, bool]:
    """Mandatory startup check: verifies configured models in production mode (spec/05 §5.1).

    In production mode only, verifies that each configured model ID:
      - CLAUDE_MODEL_FAST
      - CLAUDE_MODEL_SMART
      - CLAUDE_MODEL_BUILD
    works by making one minimal test call per model.
    Fails fast with an explicit error naming the env var if rejected;
    DO NOT auto-substitute model names.
    """
    if not force and settings.ENVIRONMENT != "production":
        logger.info(
            "Skipping model startup check in non-production environment: %s",
            settings.ENVIRONMENT,
        )
        return {}

    if not settings.ANTHROPIC_API_KEY:
        raise ModelConfigurationError(
            "ANTHROPIC_API_KEY is not configured in production mode. "
            "Please configure ANTHROPIC_API_KEY in your environment."
        )

    model_env_vars = [
        ("CLAUDE_MODEL_FAST", settings.CLAUDE_MODEL_FAST),
        ("CLAUDE_MODEL_SMART", settings.CLAUDE_MODEL_SMART),
        ("CLAUDE_MODEL_BUILD", settings.CLAUDE_MODEL_BUILD),
    ]

    client = get_anthropic_client()

    results: dict[str, bool] = {}
    tested_models: dict[str, bool] = {}

    for env_var, model_id in model_env_vars:
        if not model_id or not model_id.strip():
            raise ModelConfigurationError(
                f"Configured model for {env_var} is empty. "
                f"Please specify a valid Claude model ID in {env_var}."
            )

        if model_id in tested_models:
            results[env_var] = tested_models[model_id]
            continue

        try:
            logger.info("Testing model ID '%s' configured in %s...", model_id, env_var)
            await client.messages.create(
                model=model_id,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            tested_models[model_id] = True
            results[env_var] = True
        except Exception as exc:
            tested_models[model_id] = False
            error_msg = (
                f"Configured model '{model_id}' failed startup check for {env_var}: {exc}. "
                f"Please check and fix the {env_var} environment variable. "
                f"Do not auto-substitute model names."
            )
            logger.critical(error_msg)
            raise ModelConfigurationError(error_msg) from exc

    return results


verify_production_models = verify_configured_models
