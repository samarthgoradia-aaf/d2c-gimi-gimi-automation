"""
fetch_meta.py  —  gets raw Meta (Facebook) Ads numbers.

Produces one row per ad per day over the last WINDOW_DAYS, reshaped into the
RAW_Meta column layout (keys = config.RAW_META_COLUMNS).

Two ways to get the data, picked automatically:
  * Composio  (default when COMPOSIO_API_KEY is set) — Composio owns the
    Facebook OAuth connection and token refresh, so there is no access token
    to generate or renew. Meta's insights tool has no "one row per day" option,
    so we ask for each day separately across the window.
  * Direct Marketing API  (when META_ACCESS_TOKEN is set instead) — a single
    call with time_increment=1, paginated. Kept as a fallback.

Run it on its own to test and save a sample:
     python fetch_meta.py
"""
import json
import os

import requests

import config
from utils import PipelineError, require_env, date_window, log, save_sample

# ── shared bits ─────────────────────────────────────────────────────────────

_FIELDS = [
    "campaign_name", "adset_name", "ad_name", "spend", "impressions", "reach",
    "frequency", "inline_link_clicks", "actions", "action_values",
    "video_thruplay_watched_actions", "video_p25_watched_actions",
    "video_p50_watched_actions", "video_p75_watched_actions",
    "video_p100_watched_actions",
]

# Only GG_ campaigns, and only rows that actually had impressions.
_FILTERING = [
    {"field": "campaign.name", "operator": "CONTAIN", "value": "GG_"},
    {"field": "impressions", "operator": "GREATER_THAN", "value": 0},
]


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _amap(items):
    """Turn an 'actions' / 'action_values' list into {action_type: number}."""
    out = {}
    for a in items or []:
        out[a.get("action_type")] = _num(a.get("value"))
    return out


def _pick(m, *keys):
    """First matching action type, else 0. Handles the omni_* / plain names."""
    for k in keys:
        if k in m:
            return m[k]
    return 0.0


def _video(items):
    """The 'video_view' value inside a video_*_watched_actions list."""
    for a in items or []:
        if a.get("action_type") == "video_view":
            return _num(a.get("value"))
    return 0.0


def _shape(r, fallback_date=None):
    """One raw Meta insights row -> one RAW_Meta row dict."""
    am = _amap(r.get("actions"))
    avm = _amap(r.get("action_values"))
    return {
        "date": r.get("date_start") or fallback_date,
        "campaign": r.get("campaign_name", ""),
        "adset": r.get("adset_name", ""),
        "ad": r.get("ad_name", ""),
        "spend": round(_num(r.get("spend")), 2),
        "impressions": round(_num(r.get("impressions")), 2),
        "reach": round(_num(r.get("reach")), 2),
        "frequency": round(_num(r.get("frequency")), 2),
        "link_clicks": round(_num(r.get("inline_link_clicks")), 2),
        "lpv": round(_pick(am, "landing_page_view"), 2),
        "atc": round(_pick(am, "omni_add_to_cart", "add_to_cart"), 2),
        "checkout": round(_pick(am, "omni_initiated_checkout", "initiate_checkout"), 2),
        "purchases": round(_pick(am, "omni_purchase", "purchase"), 2),
        "revenue": round(_pick(avm, "omni_purchase", "purchase"), 2),
        "video_3s": round(_pick(am, "video_view"), 2),
        "thruplay": round(_video(r.get("video_thruplay_watched_actions")), 2),
        "p25": round(_video(r.get("video_p25_watched_actions")), 2),
        "p50": round(_video(r.get("video_p50_watched_actions")), 2),
        "p75": round(_video(r.get("video_p75_watched_actions")), 2),
        "p100": round(_video(r.get("video_p100_watched_actions")), 2),
    }


def _finish(rows):
    if not rows:
        raise PipelineError(
            "Meta returned zero ad rows for the window. Either there was no "
            "spend at all, the connection lost access to the ad account, or "
            "the campaign-name filter matched nothing. See TROUBLESHOOTING.md "
            "-> 'Meta empty'."
        )
    rows.sort(key=lambda x: (x["date"], x["campaign"], x["adset"], x["ad"]))
    n_days = len({r["date"] for r in rows})
    log(f"Meta: {len(rows)} ad-day rows across {n_days} days")
    return rows


# ── path 1: Composio ────────────────────────────────────────────────────────

def _iter_days(since, until):
    from datetime import date, timedelta
    d0 = date.fromisoformat(since)
    d1 = date.fromisoformat(until)
    d = d0
    while d <= d1:
        yield d.isoformat()
        d += timedelta(days=1)


def _fetch_via_composio():
    from composio_bridge import execute

    since, until = date_window()
    log(f"Meta via Composio: requesting {since} .. {until} (one call per day)")
    rows = []
    for day in _iter_days(since, until):
        # NOTE: argument names below are the expected ones for
        # METAADS_GET_INSIGHTS. Run `python probe_composio.py` once to confirm
        # them against the live schema and adjust if needed.
        args = {
            "object_id": config.META_AD_ACCOUNT_ID,
            "level": "ad",
            "time_range": {"since": day, "until": day},
            "fields": _FIELDS,
            "filtering": _FILTERING,
            "limit": 500,
        }
        after = None
        while True:
            if after:
                args["after"] = after
            data = execute("METAADS_GET_INSIGHTS", args)
            batch = data.get("data", data) if isinstance(data, dict) else data
            for r in batch or []:
                rows.append(_shape(r, fallback_date=day))
            paging = data.get("paging", {}) if isinstance(data, dict) else {}
            after = (paging.get("cursors") or {}).get("after")
            if not after or not paging.get("next"):
                break
    return _finish(rows)


# ── path 2: direct Marketing API (fallback) ────────────────────────────────

_BASE = f"https://graph.facebook.com/{config.META_API_VERSION}"


def _get(url, params):
    resp = requests.get(url, params=params, timeout=120)
    if resp.status_code in (400, 401, 403) and (
        "OAuth" in resp.text or "access token" in resp.text.lower()
    ):
        raise PipelineError(
            "Meta rejected the access token. It has expired, been revoked, or "
            "lost the 'ads_read' permission / access to the ad account. See "
            "TROUBLESHOOTING.md -> 'Meta token'."
        )
    if resp.status_code != 200:
        raise PipelineError(
            f"Meta API returned HTTP {resp.status_code}. First part of the "
            f"response: {resp.text[:600]}"
        )
    return resp.json()


def _fetch_via_direct():
    token = require_env("META_ACCESS_TOKEN")
    since, until = date_window()
    log(f"Meta via direct API: requesting {since} .. {until}")

    params = {
        "level": "ad",
        "time_increment": 1,
        "time_range": json.dumps({"since": since, "until": until}),
        "filtering": json.dumps(_FILTERING),
        "fields": ",".join(_FIELDS),
        "limit": 500,
        "access_token": token,
    }
    url = f"{_BASE}/{config.META_AD_ACCOUNT_ID}/insights"

    raw = []
    body = _get(url, params)
    page = 1
    while True:
        raw.extend(body.get("data", []))
        nxt = (body.get("paging") or {}).get("next")
        if not nxt:
            break
        page += 1
        log(f"Meta: fetching page {page}")
        body = _get(nxt, None)

    return _finish([_shape(r) for r in raw])


# ── entry point ────────────────────────────────────────────────────────────

def fetch(token=None):
    if os.environ.get("COMPOSIO_API_KEY", "").strip():
        return _fetch_via_composio()
    return _fetch_via_direct()


if __name__ == "__main__":
    save_sample("meta", fetch())
