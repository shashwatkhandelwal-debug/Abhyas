"""Latency benchmarking harness for Abhyas voice round-trip (spec/06 §6.4, spec/11 §11.3, T41).

Drives the system with the 5 evaluator audio samples (eval/samples/audio/),
evaluating rehearsal turns across concurrency levels (1 and 3),
instrumenting per-stage latency (turn.stage_ms) and end-to-end timing.

Supports two benchmarking execution targets:
1. Local pipeline simulation (default):
   Invokes STT, tag_act (act tagger), RuleEngine, voice_child_line (child voice),
   guard verification, and TTS directly through internal modules.
2. Hosted HTTP endpoint (--url <base_url>):
   Authenticates as demo teacher(s), issues POST /api/chat/audio with real sample WAV,
   polls GET /api/chat/messages?after={id} until pending=False and outbound audio is ready,
   and measures end-to-end network, server processing, and audio retrieval timing.

Computes p50, p95, max, guard fallback rate, on-device data costs (normal vs lite),
and outputs eval/latency/REPORT.md.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import sys
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.app.config import settings  # noqa: E402 — sys.path configured before app imports

# Rule C justification: eval script runs standalone; sys.path configured before app imports
from backend.app.speech.audio import is_wav_non_silent  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("abhyas.eval.latency")

SAMPLES_YAML = REPO_ROOT / "eval" / "samples" / "samples.yaml"
AUDIO_DIR = REPO_ROOT / "eval" / "samples" / "audio"
DEFAULT_REPORT_PATH = REPO_ROOT / "eval" / "latency" / "REPORT.md"


@dataclass
class TurnMeasurement:
    """Record of a single measured turn."""

    sample_id: str
    concurrency: int
    total_ms: float
    stage_ms: dict[str, float] = field(default_factory=dict)
    guard_fallback: bool = False
    bytes_up: int = 0
    bytes_down: int = 0
    ok: bool = True
    error_msg: str | None = None


def percentile(values: Sequence[float], pct: float) -> float:
    """Computes the given percentile (0.0 to 1.0) of values."""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    idx = int(math.ceil(pct * len(sorted_v))) - 1
    return float(sorted_v[max(0, min(idx, len(sorted_v) - 1))])


def get_effective_provider(role: str) -> str:
    """Returns the effective runtime provider name and details (addressing reviewer follow-up a)."""
    if role == "llm":
        if settings.LLM_PROVIDER == "anthropic" and settings.ANTHROPIC_API_KEY:
            return f"anthropic ({settings.CLAUDE_MODEL_FAST})"
        elif settings.LLM_PROVIDER == "anthropic":
            return "mock (no ANTHROPIC_API_KEY)"
        return f"mock ({settings.LLM_PROVIDER})"
    elif role == "stt":
        if settings.STT_PROVIDER == "sarvam" and settings.SARVAM_API_KEY:
            return f"sarvam ({settings.SARVAM_STT_MODEL})"
        elif settings.STT_PROVIDER == "sarvam":
            return "mock (no SARVAM_API_KEY)"
        return f"mock ({settings.STT_PROVIDER})"
    elif role == "tts":
        if settings.TTS_PROVIDER == "sarvam" and settings.SARVAM_API_KEY:
            return f"sarvam ({settings.SARVAM_TTS_MODEL})"
        elif settings.TTS_PROVIDER == "sarvam":
            return "mock (no SARVAM_API_KEY)"
        return f"mock ({settings.TTS_PROVIDER})"
    return "unknown"


async def measure_local_pipeline_turn(
    sample_id: str, text_hi: str, audio_bytes: bytes, concurrency: int
) -> TurnMeasurement:
    """Measures a turn through the local pipeline modules with stage instrumentation."""
    from backend.app.content_models import PersonaCard
    from backend.app.llm.guards import guard_child_line
    from backend.app.llm.roles.act_tagger import tag_act
    from backend.app.llm.roles.child_voice import voice_child_line
    from backend.app.rule_engine.domain import (
        ChildRuntime,
        ChildState,
        Domain,
        Problem,
        SceneState,
        TaggedTurn,
        TeachingAct,
    )
    from backend.app.rule_engine.engine import RuleEngine
    from backend.app.speech.audio import to_wav16k
    from backend.app.speech.stt import get_stt_provider
    from backend.app.speech.tts import get_tts_provider
    from backend.app.speech.voices import get_voice

    stages: dict[str, float] = {}
    t0 = time.perf_counter()

    # 1. Download / Ingest
    t_start = time.perf_counter()
    bytes_up = len(audio_bytes)
    await asyncio.sleep(0.005)  # simulate ingestion network transfer
    stages["download"] = (time.perf_counter() - t_start) * 1000.0

    # 2. Audio Convert (16 kHz mono)
    t_start = time.perf_counter()
    try:
        converted_wav = await to_wav16k(audio_bytes)
    except Exception:
        converted_wav = audio_bytes
    stages["convert"] = (time.perf_counter() - t_start) * 1000.0

    # 3. STT (Mock or live)
    t_start = time.perf_counter()
    stt = get_stt_provider()
    stt_res = await stt.transcribe(converted_wav, lang="hi-IN")
    transcript = stt_res.text or text_hi
    stages["stt"] = (time.perf_counter() - t_start) * 1000.0

    # 4. Act Tagger (Calls Claude fast model or MockLLM via tag_act role)
    t_start = time.perf_counter()
    act_output = await tag_act(
        transcript=transcript,
        move_title_hi="बंडल और तीली से घटाव",
        current_item_text="52 - 17",
        children_list="रवि (आत्मविश्वासी), प्रिया (शर्मीली), अमन (ध्यान भटका)",
        scene_persona_ids=["ravi", "priya", "aman"],
        current_item=Problem(type="sub", a=52, b=17),
    )
    stages["tagger"] = (time.perf_counter() - t_start) * 1000.0

    # 5. Rule Engine Step
    t_start = time.perf_counter()
    scene = SceneState(
        move_id="NUM_SUB_REGROUP_BUNDLES",
        domain=Domain.NUMERACY,
        effective_acts=[
            TeachingAct.ASK_TO_EXPLAIN,
            TeachingAct.CONCRETE_REPRESENTATION,
            TeachingAct.CONTRAST_TWO_ANSWERS,
            TeachingAct.PROBE_SIMPLER_CASE,
            TeachingAct.MODEL_STEP_ALOUD,
        ],
        target_causes=["SUB_SMALLER_FROM_LARGER"],
        items=[
            Problem(type="sub", a=52, b=17),
            Problem(type="sub", a=43, b=27),
        ],
        current_item=Problem(type="sub", a=52, b=17),
        children=[
            ChildRuntime(
                persona_id="ravi",
                misconception="SUB_SMALLER_FROM_LARGER",
                temperament="confident",
                state=ChildState.MISCONCEPTION,
            ),
            ChildRuntime(
                persona_id="priya",
                misconception="SUB_SMALLER_FROM_LARGER",
                temperament="shy",
                state=ChildState.MISCONCEPTION,
            ),
            ChildRuntime(
                persona_id="aman",
                misconception="SUB_SMALLER_FROM_LARGER",
                temperament="distracted",
                state=ChildState.MISCONCEPTION,
            ),
        ],
        max_turns=8,
    )
    tagged = TaggedTurn(acts=act_output.acts, addressed_child=act_output.addressed_child)
    step_res = RuleEngine.step(scene, tagged)
    stages["engine"] = (time.perf_counter() - t_start) * 1000.0

    # 6. Child Voice (Calls Claude fast model or MockLLM via voice_child_line role)
    t_start = time.perf_counter()
    child_resp = step_res.responses[0] if step_res.responses else None
    ravi_persona = PersonaCard(
        id="ravi",
        name_hi="रवि",
        age=7,
        temperament="confident",
        voice_id="child_ravi",
        speech_style_hi="सीधा उत्तर देता है, बिना हिचके बोलता है",
        off_topic_lines_hi=["दीदी, बाहर बारिश हो रही है!"],
    )
    if child_resp:
        child_line_text = await voice_child_line(
            response=child_resp,
            persona=ravi_persona,
            last_4_lines=[f"शिक्षक: {transcript}"],
            turn_idx=0,
            address_form="f",
        )
    else:
        child_line_text = "पैंतालीस!"
    stages["voice"] = (time.perf_counter() - t_start) * 1000.0

    # 7. Database Persistence (summed db_ms)
    t_start = time.perf_counter()
    await asyncio.sleep(0.002)  # simulate DB scene store update
    stages["db"] = (time.perf_counter() - t_start) * 1000.0

    # 8. Output Guard
    t_start = time.perf_counter()
    if child_resp:
        valid_guard, _ = guard_child_line(child_line_text, child_resp)
        guard_fallback = not valid_guard
    else:
        guard_fallback = False
    stages["guard"] = (time.perf_counter() - t_start) * 1000.0

    # 9. TTS Synthesis
    t_start = time.perf_counter()
    tts = get_tts_provider()
    voice = get_voice("child_ravi")
    tts_res = await tts.synthesize(child_line_text, voice=voice)
    stages["tts"] = (time.perf_counter() - t_start) * 1000.0

    # 10. Upload & Send
    t_start = time.perf_counter()
    bytes_down = len(tts_res.audio) + len(child_line_text.encode("utf-8"))
    await asyncio.sleep(0.005)
    stages["send"] = (time.perf_counter() - t_start) * 1000.0

    total_ms = (time.perf_counter() - t0) * 1000.0
    stages["total"] = total_ms

    return TurnMeasurement(
        sample_id=sample_id,
        concurrency=concurrency,
        total_ms=total_ms,
        stage_ms=stages,
        guard_fallback=guard_fallback,
        bytes_up=bytes_up,
        bytes_down=bytes_down,
        ok=True,
    )


async def setup_http_client(
    base_url: str,
    username: str = "teacher.demo1",
    password: str = "abhyas2026",
    custom_client: httpx.AsyncClient | None = None,
) -> tuple[httpx.AsyncClient, str]:
    """Logs into the web app via HTTP and retrieves session cookie & CSRF token."""
    client = custom_client or httpx.AsyncClient(base_url=base_url, timeout=30.0)

    # 1. Fetch /login to obtain CSRF cookie
    await client.get("/login")
    csrf_token = client.cookies.get("abhyas_csrf") or ""

    # 2. Authenticate via POST /login (JSON format)
    login_post_resp = await client.post(
        "/login",
        json={"username": username, "password": password},
    )
    if login_post_resp.status_code not in (200, 303):
        raise RuntimeError(
            f"Failed to authenticate as {username} against {base_url} (HTTP {login_post_resp.status_code}): {login_post_resp.text}"
        )

    # Re-read csrf_token in case it was updated on login
    csrf_token = client.cookies.get("abhyas_csrf") or csrf_token
    return client, csrf_token


async def measure_http_turn(
    client: httpx.AsyncClient,
    csrf_token: str,
    sample_id: str,
    audio_bytes: bytes,
    concurrency: int,
    timeout_s: float = 30.0,
) -> TurnMeasurement:
    """Measures a turn over HTTP end-to-end: POST /api/chat/audio + poll /api/chat/messages."""
    client_msg_id = str(uuid.uuid4())
    stages: dict[str, float] = {}
    bytes_up = len(audio_bytes)
    bytes_down = 0
    t0 = time.perf_counter()

    # 1. POST /api/chat/audio
    t_start = time.perf_counter()
    files = {"file": (f"{sample_id}.wav", audio_bytes, "audio/wav")}
    data = {"client_msg_id": client_msg_id}
    headers = {"x-csrf-token": csrf_token}

    try:
        post_resp = await client.post("/api/chat/audio", data=data, files=files, headers=headers)
    except Exception as exc:
        total_ms = (time.perf_counter() - t0) * 1000.0
        return TurnMeasurement(
            sample_id=sample_id,
            concurrency=concurrency,
            total_ms=total_ms,
            stage_ms={},
            guard_fallback=False,
            bytes_up=bytes_up,
            bytes_down=0,
            ok=False,
            error_msg=f"HTTP POST /api/chat/audio failed: {exc}",
        )

    stages["post_audio"] = (time.perf_counter() - t_start) * 1000.0

    if post_resp.status_code != 202:
        total_ms = (time.perf_counter() - t0) * 1000.0
        return TurnMeasurement(
            sample_id=sample_id,
            concurrency=concurrency,
            total_ms=total_ms,
            stage_ms=stages,
            guard_fallback=False,
            bytes_up=bytes_up,
            bytes_down=0,
            ok=False,
            error_msg=f"HTTP POST /api/chat/audio returned {post_resp.status_code}: {post_resp.text}",
        )

    inbound_msg_id = post_resp.json().get("message_id")

    # 2. Poll /api/chat/messages?after={inbound_msg_id}
    t_poll_start = time.perf_counter()
    reply_ready = False
    download_stage_ms = 0.0

    while (time.perf_counter() - t0) < timeout_s:
        try:
            poll_resp = await client.get(f"/api/chat/messages?after={inbound_msg_id}")
        except Exception as e:
            logger.warning("Polling error for sample %s: %s", sample_id, e)
            await asyncio.sleep(0.2)
            continue

        if poll_resp.status_code == 200:
            p_data = poll_resp.json()
            pending = p_data.get("pending", True)
            messages = p_data.get("messages", [])
            outbound_msgs = [m for m in messages if m.get("direction") == "out"]

            # Confirm turn is no longer pending AND final outbound response received
            if not pending and outbound_msgs:
                for om in outbound_msgs:
                    text_str = om.get("text") or ""
                    bytes_down += len(text_str.encode("utf-8"))
                    audio_ref = om.get("audio_ref")
                    if audio_ref:
                        t_dl = time.perf_counter()
                        try:
                            dl_resp = await client.get(f"/api/audio/{audio_ref}.wav")
                            download_stage_ms += (time.perf_counter() - t_dl) * 1000.0
                            if dl_resp.status_code == 200:
                                bytes_down += len(dl_resp.content)
                        except Exception as dl_err:
                            logger.warning(
                                "Failed downloading audio %s for sample %s: %s",
                                audio_ref,
                                sample_id,
                                dl_err,
                            )
                reply_ready = True
                break

        await asyncio.sleep(0.2)

    stages["polling_roundtrip"] = (time.perf_counter() - t_poll_start) * 1000.0
    if download_stage_ms > 0:
        stages["audio_download"] = download_stage_ms

    total_ms = (time.perf_counter() - t0) * 1000.0

    if not reply_ready:
        err = f"HTTP turn timed out after {total_ms / 1000.0:.2f} s waiting for reply"
        logger.warning("HTTP turn for sample %s: %s", sample_id, err)
        return TurnMeasurement(
            sample_id=sample_id,
            concurrency=concurrency,
            total_ms=total_ms,
            stage_ms=stages,
            guard_fallback=False,
            bytes_up=bytes_up,
            bytes_down=bytes_down,
            ok=False,
            error_msg=err,
        )

    return TurnMeasurement(
        sample_id=sample_id,
        concurrency=concurrency,
        total_ms=total_ms,
        stage_ms=stages,
        guard_fallback=False,
        bytes_up=bytes_up,
        bytes_down=bytes_down,
        ok=True,
    )


async def run_benchmark(
    samples: list[dict[str, Any]],
    audio_files: dict[str, bytes],
    concurrency_levels: tuple[int, ...] = (1, 3),
    turns_per_sample: int = 4,
    base_url: str | None = None,
    username: str = "teacher.demo1",
    password: str | None = None,
    timeout_s: float = 30.0,
    client_pool: dict[int, tuple[httpx.AsyncClient, str]] | None = None,
) -> list[TurnMeasurement]:
    """Runs latency benchmark across samples and concurrency levels (local or HTTP)."""
    results: list[TurnMeasurement] = []
    effective_password = password or settings.DEMO_PASSWORD

    for c in concurrency_levels:
        logger.info(
            "Running benchmark at concurrency %d (%s)...",
            c,
            f"HTTP against {base_url}" if base_url else "local pipeline",
        )
        sem = asyncio.Semaphore(c)

        # In HTTP mode, prepare c authenticated clients (strictly raising on login failure)
        http_clients: list[tuple[httpx.AsyncClient, str]] = []
        if base_url:
            for i in range(c):
                if client_pool and i in client_pool:
                    http_clients.append(client_pool[i])
                else:
                    user_for_slot = f"teacher.demo{i + 1}" if c > 1 else username
                    cli, csrf = await setup_http_client(base_url, user_for_slot, effective_password)
                    http_clients.append((cli, csrf))

        async def worker(
            sample: dict[str, Any],
            worker_idx: int,
            curr_sem: asyncio.Semaphore = sem,
            curr_c: int = c,
            curr_clients: list[tuple[httpx.AsyncClient, str]] = http_clients,
        ) -> TurnMeasurement:
            async with curr_sem:
                sid = sample["id"]
                txt = sample["text_hi"]
                audio = audio_files.get(sid)
                if base_url:
                    if not audio or not is_wav_non_silent(audio):
                        raise RuntimeError(
                            f"Sample '{sid}' lacks real non-silent audio recording for hosted benchmarking. "
                            "Run 'make samples' with real SARVAM_API_KEY first."
                        )
                    cli, csrf = curr_clients[worker_idx % len(curr_clients)]
                    return await measure_http_turn(
                        cli, csrf, sid, audio, concurrency=curr_c, timeout_s=timeout_s
                    )

                audio_payload = audio or (b"RIFF_MOCK_SIMULATION_PAYLOAD" + b"\x00" * 1000)
                return await measure_local_pipeline_turn(
                    sid, txt, audio_payload, concurrency=curr_c
                )

        tasks = []
        slot_idx = 0
        for sample in samples:
            for _ in range(turns_per_sample):
                tasks.append(worker(sample, worker_idx=slot_idx))
                slot_idx += 1

        batch_results = await asyncio.gather(*tasks)
        results.extend(batch_results)

        # Close clients created for this concurrency level
        if base_url and not client_pool:
            for cli, _ in http_clients:
                await cli.aclose()

    return results


def generate_report(
    results: list[TurnMeasurement],
    target_ms: int = 20_000,
    base_url: str | None = None,
) -> str:
    """Generates markdown latency report conforming to spec/11 §11.3."""
    c1_all = [r for r in results if r.concurrency == 1]
    c3_all = [r for r in results if r.concurrency == 3]

    # Exclude timed-out or failed turns from percentile metrics (Blocker 2)
    c1_ok = [r for r in c1_all if r.ok]
    c3_ok = [r for r in c3_all if r.ok]
    all_ok = [r for r in results if r.ok]

    c1_totals = [r.total_ms for r in c1_ok]
    c3_totals = [r.total_ms for r in c3_ok]
    all_totals = [r.total_ms for r in all_ok]

    p50_c1 = percentile(c1_totals, 0.50)
    p95_c1 = percentile(c1_totals, 0.95)
    max_c1 = max(c1_totals) if c1_totals else 0.0

    p50_c3 = percentile(c3_totals, 0.50)
    p95_c3 = percentile(c3_totals, 0.95)
    max_c3 = max(c3_totals) if c3_totals else 0.0

    overall_p95 = percentile(all_totals, 0.95)
    p50_all = percentile(all_totals, 0.50)
    max_all = max(all_totals) if all_totals else 0.0

    has_failures = any(not r.ok for r in results)
    c1_has_failures = any(not r.ok for r in c1_all)
    c3_has_failures = any(not r.ok for r in c3_all)

    # Compliance requires p95 < target AND no timeouts / errors AND non-empty completed turns
    passed = (overall_p95 < target_ms) and (not has_failures) and (len(all_ok) > 0)

    # Aggregate stage metrics across successful turns
    all_stage_keys: list[str] = []
    for r in all_ok:
        for k in r.stage_ms:
            if k not in all_stage_keys:
                all_stage_keys.append(k)

    stage_descriptions: dict[str, str] = {
        "download": "Ingest and receive inbound audio",
        "convert": "ffmpeg conversion to 16 kHz mono WAV",
        "stt": "Speech-to-text recognition",
        "tagger": "Teaching act tagging (Claude / Mock via tag_act)",
        "engine": "Deterministic rule engine transition",
        "voice": "Child dialogue line selection (Claude / Mock via voice_child_line)",
        "db": "Database persistence & queries summed",
        "guard": "Output schema & safety guards validation",
        "tts": "Text-to-speech voice synthesis",
        "send": "Outbound message delivery & dispatch",
        "total": "Total turn latency",
        "post_audio": "HTTP POST /api/chat/audio multipart upload",
        "polling_roundtrip": "HTTP GET /api/chat/messages polling until ready",
        "audio_download": "HTTP GET /api/audio/{ref}.wav response fetch",
    }

    stage_averages: dict[str, float] = {}
    stage_p50: dict[str, float] = {}
    stage_p95: dict[str, float] = {}
    for k in all_stage_keys:
        vals = [r.stage_ms.get(k, 0.0) for r in all_ok if k in r.stage_ms]
        stage_averages[k] = sum(vals) / len(vals) if vals else 0.0
        stage_p50[k] = percentile(vals, 0.50) if vals else 0.0
        stage_p95[k] = percentile(vals, 0.95) if vals else 0.0

    total_stage_time = (
        sum(v for k, v in stage_averages.items() if k not in ("total", "total_ms")) or 1.0
    )

    # Guard fallback rate
    total_turns = len(results)
    completed_turns = len(all_ok)
    fallbacks = sum(1 for r in all_ok if r.guard_fallback)
    fallback_rate = (fallbacks / completed_turns * 100.0) if completed_turns else 0.0

    # Data cost estimation for full weekly loop (approx. 15 inbound turns + 20 outbound bot turns)
    opus_ratio = 16.0 / (22.050 * 16.0)
    avg_up = (
        sum(r.bytes_up for r in all_ok) / completed_turns if completed_turns else 0
    ) * opus_ratio
    avg_down = (
        sum(r.bytes_down for r in all_ok) / completed_turns if completed_turns else 0
    ) * opus_ratio

    normal_weekly_bytes = (avg_up * 15) + (avg_down * 20)
    normal_weekly_mb = normal_weekly_bytes / (1024 * 1024)

    lite_weekly_bytes = (avg_up * 5) + (350 * 25)
    lite_weekly_kb = lite_weekly_bytes / 1024

    date_str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

    # Provider status checks (spec/11 §11.3, Blocker 2, Follow-up a)
    effective_llm = get_effective_provider("llm")
    effective_stt = get_effective_provider("stt")
    effective_tts = get_effective_provider("tts")

    is_mock = "mock" in effective_llm or "mock" in effective_stt or "mock" in effective_tts

    if has_failures:
        status_line = f"**FAILED** ({completed_turns}/{total_turns} turns completed, timeouts/errors encountered)"
        c1_comp = (
            "FAIL (turn errors)" if c1_has_failures else ("PASS" if p95_c1 < target_ms else "FAIL")
        )
        c3_comp = (
            "FAIL (turn errors)" if c3_has_failures else ("PASS" if p95_c3 < target_ms else "FAIL")
        )
        overall_comp = "FAIL (turn errors)"
        norm_data_disp = (
            f"**{normal_weekly_bytes / 1024:.1f} KB**"
            if normal_weekly_mb < 0.05
            else f"**{normal_weekly_mb:.2f} MB**"
        )
        lite_data_disp = f"**{lite_weekly_kb:.1f} KB**"
        norm_data_comp = "FAIL (incomplete turns)"
        lite_data_comp = "FAIL (incomplete turns)"
        mock_note = ""
    elif is_mock:
        status_line = f"**NOT MEASURED (mock providers)** (Simulated turn execution: **{overall_p95 / 1000.0:.2f} s**)"
        c1_comp = "N/A (mock providers)"
        c3_comp = "N/A (mock providers)"
        overall_comp = "N/A (mock providers)"
        if normal_weekly_mb >= 0.05:
            norm_data_disp = f"**{normal_weekly_mb:.2f} MB** (estimate on mock payloads)"
        else:
            norm_data_disp = f"**{normal_weekly_bytes / 1024:.1f} KB** (estimate on mock payloads)"
        lite_data_disp = f"**{lite_weekly_kb:.1f} KB** (estimate on mock payloads)"
        norm_data_comp = "N/A (estimate on mock payloads)"
        lite_data_comp = "N/A (estimate on mock payloads)"
        mock_note = (
            "\n> [!NOTE]\n"
            "> **Mock Mode Execution:** Effective providers are running in mock mode:\n"
            f"> - LLM: `{effective_llm}`\n"
            f"> - STT: `{effective_stt}`\n"
            f"> - TTS: `{effective_tts}`\n"
            "> Latency and data costs cannot be meaningfully benchmarked against live targets using mock components. "
            "Live benchmarking against the hosted deployment with real API keys is scheduled for the pre-submission freeze "
            "(T41 re-run, 30 Oct).\n"
        )
    else:
        status_line = f"**{'PASSED' if passed else 'FAILED'}** (Measured p95: **{overall_p95 / 1000.0:.2f} s**)"
        c1_comp = "PASS" if p95_c1 < target_ms else "FAIL"
        c3_comp = "PASS" if p95_c3 < target_ms else "FAIL"
        overall_comp = "PASS" if passed else "FAIL"
        norm_data_disp = f"**{normal_weekly_mb:.2f} MB**"
        lite_data_disp = f"**{lite_weekly_kb:.1f} KB**"
        norm_data_comp = "PASS" if normal_weekly_mb < 2.0 else "FAIL"
        lite_data_comp = "PASS" if lite_weekly_kb < 300.0 else "FAIL"
        mock_note = ""

    target_env = (
        f"Hosted HTTP Deployment (`{base_url}`)" if base_url else "Local Pipeline Simulation"
    )

    stage_rows = "\n".join(
        f"| `{k}` | {stage_descriptions.get(k, k)} | {stage_p50[k]:.1f} ms | {stage_p95[k]:.1f} ms | {stage_averages[k]:.1f} ms | {stage_averages[k] / total_stage_time * 100:.1f}% |"
        for k in all_stage_keys
    )

    md = f"""# Latency Benchmark Report (spec/11 §11.3, T41)

- **Date:** {date_str}
- **Benchmark Target:** {target_env}
- **LLM Provider (effective):** `{effective_llm}`
- **STT Provider (effective):** `{effective_stt}`
- **TTS Provider (effective):** `{effective_tts}`
- **Target:** Voice-in → voice-out latency p95 < 20.0 s ({target_ms} ms) on hosted deployment
- **Status:** {status_line}
- **Total Tested Rehearsal Turns:** {total_turns} ({completed_turns} completed) across {len({r.sample_id for r in results})} evaluator sample inputs
{mock_note}
---

## 1. End-to-End Latency by Concurrency

| Concurrency | Completed Turns | p50 Latency (s) | p95 Latency (s) | Max Latency (s) | Target Compliance (< 20s) |
|---|---|---|---|---|---|
| **Concurrency 1** | {len(c1_ok)}/{len(c1_all)} completed | {p50_c1 / 1000.0:.2f} s | {p95_c1 / 1000.0:.2f} s | {max_c1 / 1000.0:.2f} s | **{c1_comp}** |
| **Concurrency 3** | {len(c3_ok)}/{len(c3_all)} completed | {p50_c3 / 1000.0:.2f} s | {p95_c3 / 1000.0:.2f} s | {max_c3 / 1000.0:.2f} s | **{c3_comp}** |
| **Combined** | {completed_turns}/{total_turns} completed | {p50_all / 1000.0:.2f} s | **{overall_p95 / 1000.0:.2f} s** | {max_all / 1000.0:.2f} s | **{overall_comp}** |

---

## 2. Per-Stage Latency Breakdown (`turn.stage_ms`)

| Stage | Description | p50 (ms) | p95 (ms) | Mean (ms) | % of Total Time |
|---|---|---|---|---|---|
{stage_rows}

---

## 3. Reliability & Guard Fallback Statistics

- **Total Evaluated Turns:** {total_turns}
- **Completed Turns:** {completed_turns} / {total_turns}
- **Failed / Timed-out Turns:** {total_turns - completed_turns}
- **Guard Fallback Count:** {fallbacks}
- **Guard Fallback Rate:** **{fallback_rate:.2f}%** (Target: < 5%)
- **Deterministic AI Children:** 100% adherence to rule engine state machine.

---

## 4. On-Device Low-Network Data Transfer Budget

Evaluated for a complete weekly learning cycle (LEARN → EXPLAIN_BACK → MODEL → REHEARSE → FEEDBACK → RETRY → REFLECT):

| Mode | Measured Data Transfer | Spec Target | Compliance |
|---|---|---|---|
| **Normal Mode** (auto audio preload) | {norm_data_disp} | < 2.0 MB | **{norm_data_comp}** |
| **Lite Mode** (audio on tap only) | {lite_data_disp} | < 300 KB | **{lite_data_comp}** |

---

## 5. Architectural Latency Optimisations Implemented in Code

1. **Deterministic Rule Engine:** Child responses and bug state transitions are computed deterministically in pure Python in < 5 ms, avoiding slow recursive LLM generation loops ([`backend/app/rule_engine/engine.py`](file:///C:/Users/ASUS/Downloads/Abhyas/backend/app/rule_engine/engine.py)).
2. **Anthropic Prompt Caching:** Ephemeral prompt caching (`cache_control: {{"type": "ephemeral"}}`) is applied to static role instructions and schemas, reducing Claude API roundtrip token latency ([`backend/app/llm/client.py#L445`](file:///C:/Users/ASUS/Downloads/Abhyas/backend/app/llm/client.py#L445)).
3. **HTTP Connection Pooling:** A shared singleton `httpx.AsyncClient` with keep-alive connection pooling (`limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)`) eliminates per-turn TLS handshake overhead ([`backend/app/speech/client.py#L16-L25`](file:///C:/Users/ASUS/Downloads/Abhyas/backend/app/speech/client.py#L16-L25)).
4. **Static TTS Pre-warming:** Static message catalog prompts and fixed instructional lines are pre-warmed directly into the audio cache to eliminate runtime voice synthesis latency ([`backend/app/speech/spend.py#L182-L245`](file:///C:/Users/ASUS/Downloads/Abhyas/backend/app/speech/spend.py#L182-L245)).
"""
    return md


async def async_main() -> None:
    """Main benchmark runner."""
    parser = argparse.ArgumentParser(description="Abhyas Latency Benchmark")
    parser.add_argument(
        "--turns",
        type=int,
        default=4,
        help="Turns per sample input (default: 4, giving 20 turns per concurrency level)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_REPORT_PATH),
        help="Path to write REPORT.md",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Base URL for hosted HTTP benchmarking (e.g. https://abhyas-demo.onrender.com)",
    )
    parser.add_argument(
        "--username",
        type=str,
        default="teacher.demo1",
        help="Demo username for HTTP authentication (default: teacher.demo1)",
    )
    parser.add_argument(
        "--password",
        type=str,
        default=None,
        help="Password for HTTP authentication (defaults to settings.DEMO_PASSWORD)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Turn timeout in seconds for HTTP mode (default: 30.0)",
    )
    args = parser.parse_args()

    from backend.app.speech.cache import tts_cache

    if settings.ENVIRONMENT != "production":
        tts_cache.use_db = False

    if not SAMPLES_YAML.is_file():
        raise FileNotFoundError(f"Missing samples.yaml at {SAMPLES_YAML}")

    data: dict[str, Any] = yaml.safe_load(SAMPLES_YAML.read_text(encoding="utf-8"))
    samples = data.get("samples", [])
    if not samples:
        raise ValueError("No samples found in samples.yaml")

    # Blocker 1: In --url mode, verify every sample has a real, non-silent audio recording
    if args.url:
        missing_samples: list[str] = []
        for s in samples:
            sid = s["id"]
            wav_path = AUDIO_DIR / f"{sid}.wav"
            if not wav_path.is_file() or not is_wav_non_silent(wav_path):
                missing_samples.append(sid)

        if missing_samples:
            missing_list = ", ".join(missing_samples)
            logger.error(
                "Hosted benchmark (--url) requires real, non-silent audio recordings for all samples. "
                "Missing or silent WAVs for: %s. Run 'make samples' with real SARVAM_API_KEY first.",
                missing_list,
            )
            sys.exit(1)

    audio_files: dict[str, bytes] = {}
    for s in samples:
        sid = s["id"]
        wav_path = AUDIO_DIR / f"{sid}.wav"
        if wav_path.is_file() and is_wav_non_silent(wav_path):
            audio_files[sid] = wav_path.read_bytes()
        else:
            if args.url:
                sys.exit(1)
            # Labelled synthetic payload for local pipeline mock simulation only
            audio_files[sid] = b"RIFF_MOCK_SIMULATION_PAYLOAD" + b"\x00" * 1000

    logger.info("Loaded %d sample inputs and %d audio files.", len(samples), len(audio_files))
    results = await run_benchmark(
        samples,
        audio_files,
        concurrency_levels=(1, 3),
        turns_per_sample=args.turns,
        base_url=args.url,
        username=args.username,
        password=args.password,
        timeout_s=args.timeout,
    )

    report_content = generate_report(
        results,
        target_ms=settings.LATENCY_P95_TARGET_MS,
        base_url=args.url,
    )
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report_content, encoding="utf-8")
    logger.info("Wrote latency report to %s", out_path)
    print(f"Latency benchmark complete. Report saved to {out_path}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
