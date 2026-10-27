"""Auxiliary keep-alive pinger for Render / hosted instances.

Pings /healthz periodically to prevent free-tier instances from spinning down
into cold sleep during evaluator review windows.

Usage:
    python scripts/keep_alive.py --url https://abhyas.onrender.com/healthz --interval 240
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import urllib.error
import urllib.request

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("keep_alive")


def ping(url: str, timeout_s: float = 10.0) -> tuple[bool, int, float]:
    start = time.monotonic()
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Abhyas-KeepAlive/1.0 (+https://abhyas.onrender.com)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            elapsed = time.monotonic() - start
            return True, resp.status, elapsed
    except urllib.error.HTTPError as err:
        elapsed = time.monotonic() - start
        return False, err.code, elapsed
    except Exception as exc:
        elapsed = time.monotonic() - start
        logger.warning("Ping error for %s: %s", url, exc)
        return False, 0, elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep Abhyas web service awake")
    parser.add_argument(
        "--url",
        default="http://localhost:8000/healthz",
        help="Health check URL (default: http://localhost:8000/healthz)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=240,
        help="Interval in seconds between pings (default: 240s / 4m)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ping once and exit immediately with status code",
    )
    args = parser.parse_args()

    logger.info("Keep-alive target: %s (interval: %ds)", args.url, args.interval)

    if args.once:
        ok, status, latency = ping(args.url)
        logger.info("Single ping: status=%d latency=%.2fs ok=%s", status, latency, ok)
        return 0 if ok else 1

    try:
        while True:
            ok, status, latency = ping(args.url)
            if ok:
                logger.info("Pulse OK: %s -> %d in %.2fs", args.url, status, latency)
            else:
                logger.warning("Pulse FAIL: %s -> %d in %.2fs", args.url, status, latency)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        logger.info("Keep-alive pinger stopped by user.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
