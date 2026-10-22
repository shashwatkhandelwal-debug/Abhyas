# Measured performance

**Date:** 2026-10-22 · **Git SHA:** `4b1dee9` plus the uncommitted `eval/measure_latency.py` and
`eval/measure_memory.py` that produced the numbers (they are committed in the next commit of branch
`feat/overnight`).

**Where these were measured.** On the developer's Windows 11 laptop (16 logical CPUs, 15.8 GB RAM, Python 3.12.10),
from this machine's home network to the Anthropic API. **Not on Render.** The hosted free instance (shared CPU,
Singapore region, 512 MB) will be slower and has a different memory profile; the numbers below say how the code
behaves, not what a judge will see. Speech (STT/TTS) is not part of any number here: no speech provider was
called, so these are not voice-in to voice-out latencies.

## 1. Latency per stage (real Claude models, no speech)

Command: `python -m eval.measure_latency` (10 scripted one-on-one scenes, 41 teacher turns; the same code path
as the app: `SceneRunner.turn`, then `coach_feedback`). Times for the three model roles are the `latency_ms` of
the app's own `llm_role` log lines; the rule engine is timed around `RuleEngine.step`. Estimated spend US$0.131.

| Stage | Calls | p50 (ms) | p95 (ms) | Fallback used |
|---|---|---|---|---|
| act_tagger (Haiku 5.5) | 41 | 1385 | 2396 | 0/41 (0%) |
| engine (rule engine, no model) | 41 | 0.1 | 0.2 | n/a |
| child_voice (Haiku 5.5) | 41 | 1236 | 1938 | 0/41 (0%) |
| coach (Sonnet 5.5) | 10 | 6966 | 15216 | 0/10 (0%) |

Share of model-role calls that used the deterministic fallback: **0 of 92 (0%)**. One coach call failed its guard
on the first attempt ("exact_words_hi must be a single sentence") and passed on the retry, which is why the
coach p95 is high; a retry is not a fallback.

Reading: one teacher turn is act_tagger then engine then child_voice, so about 2.6 s at the median on this
machine (1385 + 0.1 + 1236) and about 4.3 s at the 95th percentile of the two stages added; the coach feedback at
the end of a scene adds about 7 s at the median and up to 15 s. Network and speech time are on top. The target in
the specification is voice-in to voice-out p95 under 20 s on the hosted deployment; that has **not** been
measured (see `eval/latency/REPORT.md`, which is a mock-provider run, and `PROGRESS.md › Blocked on humans`).

## 2. Memory

Command: `python -m eval.measure_memory`. Resident set (psutil) of one Python process, **Windows**, not Linux.

| After | Resident (MB) |
|---|---|
| interpreter started | 38.3 |
| `backend.app.main` imported (all routers, clients) | 146.7 |
| retrieval index built over all chunks (1157 chunks, 5 sources + the seed chunks) | 188.0 |
| one real scene (4 turns, real models) | 193.3 |
| peak working set | 193.4 |

Headroom against Render free's 512 MB: **about 319 MB below the limit on these numbers**, i.e. the process used
about 38% of it. This is an optimistic reading: it excludes the uvicorn server and its connection pool, the
database driver's buffers, the in-process scheduler thread, and the TTS cache objects held while synthesizing,
and Linux resident sizes for the same Python packages differ from Windows ones. Treat 193 MB as a floor for
the hosted process and expect to re-measure on Render (the log shows no memory figure; the Render dashboard
does). Adding chunks (the NISHTHA FLN source added 281) grows the index roughly linearly.

## 3. Retrieval recall and off-topic rejection

Commands: `python eval/retrieval_recall.py` (offline, lexical BM25 index, no model) and
`python -m eval.guide_e2e_live --sets off,neg` (real Haiku classifier, retrieval gate, Sonnet answerer).
Questions: `eval/retrieval_questions.yaml` (40 answerable, 20 off-topic, 10 negative; evidence regexes checked
by `--verify-ground-truth`).

| Measure | Result |
|---|---|
| recall@5, any listed source (n = 40) | **0.90** (36/40); misses q20, q33, q35, q38 |
| strict recall@5, original single-source labels | 0.825 |
| recall@5 with the production score and matched-terms gate | 0.90 (same misses) |
| off-topic questions rejected by the retrieval gate alone | 12/20 |
| negative questions rejected by the gate alone | 8/10 |
| **off-topic, full pipeline with real models** | **20/20 not answered** (19 `out_of_scope`, 1 canned `admin`) |
| negative questions, full pipeline with real models | 10/10 not answered (9 `out_of_scope`, 1 `admin`) |

Honest reading: the retrieval gate alone lets 8 of 20 off-topic questions through to the answerer; it is the
classifier plus the answerer's guard that bring it to 20/20, so the rejection depends on the models being
available (with the classifier unavailable, a question falls to the gate and the answerer's guard; the last
run of that check in `PROGRESS.md` found 0 answered in that case as well). The 40 questions were written by the
team, and earlier ranking experiments were judged on the same set (`PROGRESS.md`), so recall is not an unbiased
estimate for new questions.

## How to reproduce

```
python -m eval.measure_latency --out latency.md   # needs ANTHROPIC_API_KEY, about US$0.13
python -m eval.measure_memory                     # one scene, about US$0.01
python eval/retrieval_recall.py                   # offline
python -m eval.guide_e2e_live --sets off,neg      # about 30 small calls
```
