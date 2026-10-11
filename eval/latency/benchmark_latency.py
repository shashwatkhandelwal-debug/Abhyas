"""Latency benchmarking script for WhatsApp voice round-trip (§0, §15).

Target: Voice note in -> voice reply out < 20 s for 95% of turns.
"""

from collections.abc import Sequence


def compute_p95_latency(latencies_ms: Sequence[int]) -> float:
    if not latencies_ms:
        return 0.0
    sorted_latencies = sorted(latencies_ms)
    p95_index = int(0.95 * len(sorted_latencies))
    p95_val = sorted_latencies[min(p95_index, len(sorted_latencies) - 1)]
    return float(p95_val)


if __name__ == "__main__":
    # Simulated turn latencies in ms (e.g. STT ~2s, Claude ~4s, TTS ~3s, network ~3s)
    simulated_latencies = [
        11200,
        12400,
        9800,
        14500,
        13200,
        11800,
        15600,
        10400,
        12900,
        16800,
        13400,
        14100,
        12000,
        17200,
        11500,
        18900,
        13800,
        14600,
        15200,
        19100,
    ]
    p95 = compute_p95_latency(simulated_latencies)
    print(f"P95 Latency: {p95} ms ({p95 / 1000.0:.2f} s)")
    print(f"Target < 20,000 ms: {'PASSED' if p95 < 20000 else 'FAILED'}")
