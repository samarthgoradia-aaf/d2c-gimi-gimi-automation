"""
Small shared helpers: environment loading, IST clock, the run window, a
plain-language error type, logging, and saving sample data for debugging.
"""
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

import config

# Reads a local .env file if one exists (local testing). On GitHub Actions the
# real values are already in the environment, so this quietly does nothing.
load_dotenv()


class PipelineError(Exception):
    """
    An error whose message is already written in plain language and points at
    a TROUBLESHOOTING.md section. run_pipeline.py catches these and emails the
    message as-is.
    """


def ist_now():
    """Current time in the configured timezone (Asia/Kolkata)."""
    return datetime.now(ZoneInfo(config.TIMEZONE))


def date_window():
    """
    Returns (since, until) as 'YYYY-MM-DD' strings, inclusive, in IST.
    e.g. today is 2026-09-01 and WINDOW_DAYS is 35  ->  ('2026-07-28', '2026-09-01')
    """
    today = ist_now().date()
    since = today - timedelta(days=config.WINDOW_DAYS)
    return since.isoformat(), today.isoformat()


def require_env(name):
    """Fetch an environment variable or raise a helpful PipelineError."""
    val = os.environ.get(name, "").strip()
    if not val:
        raise PipelineError(
            f"Missing setting '{name}'. For local testing add it to your .env "
            f"file. For the daily run add it in GitHub -> Settings -> Secrets "
            f"and variables -> Actions. See README.md."
        )
    return val


def log(msg):
    """Timestamped line to the console (shows up in the GitHub Actions log)."""
    print(f"{ist_now():%Y-%m-%d %H:%M:%S} IST | {msg}", flush=True)


def save_sample(name, obj):
    """
    Write a copy of fetched data to data/<name>.json so it can be inspected
    when something looks wrong. The data/ folder is git-ignored.
    """
    os.makedirs("data", exist_ok=True)
    path = os.path.join("data", f"{name}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, default=str)
    log(f"saved local copy -> {path}")
