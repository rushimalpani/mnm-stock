#!/usr/bin/env python3
"""Ping the Render API health endpoint so the free tier does not sleep.

Usage:
  python scripts/keep_render_awake.py
  python scripts/keep_render_awake.py --once
  RENDER_URL=https://your-api.onrender.com python scripts/keep_render_awake.py

Prefer the GitHub Action (.github/workflows/keep-render-awake.yml)
so this runs in the cloud every 1 and 5 minutes without your laptop.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = os.environ.get("RENDER_URL", "").rstrip("/")
INTERVAL_SEC = int(os.environ.get("KEEPALIVE_INTERVAL_SEC", "60"))  # 1 minute


def ping(base_url: str) -> bool:
    url = f"{base_url.rstrip('/')}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"[ok] {resp.status} {url} → {body}", flush=True)
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        print(f"[http-error] {exc.code} {url}", flush=True)
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"[fail] {url} → {exc}", flush=True)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Keep Render free-tier API awake")
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help="Render base URL, e.g. https://mnm-stock-api.onrender.com",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ping once and exit (used by GitHub Actions)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=INTERVAL_SEC,
        help="Seconds between pings when looping (default 300)",
    )
    args = parser.parse_args()

    if not args.url:
        print(
            "Set RENDER_URL or pass --url https://YOUR-SERVICE.onrender.com",
            file=sys.stderr,
        )
        return 2

    if args.once:
        return 0 if ping(args.url) else 1

    print(f"Keep-alive every {args.interval}s → {args.url}", flush=True)
    while True:
        ping(args.url)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
