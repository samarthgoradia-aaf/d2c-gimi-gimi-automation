"""
fetch_meta.py  —  gets raw Meta (Facebook) Ads numbers.

Calls the Marketing API for ad-level, one-row-per-day insights over the last
WINDOW_DAYS, follows pagination to the end, and reshapes each row into the
RAW_Meta column layout.

OUT: a list of dicts, one per ad per day, with the keys in
     config.RAW_META_COLUMNS.

Run it on its own to test the connection and save a sample:
     python fetch_meta.py
"""
import json

import requests

import config
from utils import PipelineError, require_env, date_window, log, save_sample

_BASE = f"https://graph.facebook.com/{config.META_API_VERSION}"

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


def fetch(token=None):
    token = token or require_env("META_ACCESS_TOKEN")
    since, until = date_window()
    log(f"Meta: requesting {since} .. {until}")

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
        body = _get(nxt, None)  # 'next' is a full URL with params baked in

    if not raw:
        raise PipelineError(
            "Meta returned zero ad rows for the window. Either there was no "
            "spend at all, or the token lost access to the ad account, or the "
            "campaign-name filter matched nothing. See TROUBLESHOOTING.md -> "
            "'Meta empty'."
        )

    rows = []
    for r in raw:
        am = _amap(r.get("actions"))
        avm = _amap(r.get("action_values"))
        rows.append({
            "date": r.get("date_start"),
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
            "checkout": round(
                _pick(am, "omni_initiated_checkout", "initiate_checkout"), 2
            ),
            "purchases": round(_pick(am, "omni_purchase", "purchase"), 2),
            "revenue": round(_pick(avm, "omni_purchase", "purchase"), 2),
            "video_3s": round(_pick(am, "video_view"), 2),
            "thruplay": round(_video(r.get("video_thruplay_watched_actions")), 2),
            "p25": round(_video(r.get("video_p25_watched_actions")), 2),
            "p50": round(_video(r.get("video_p50_watched_actions")), 2),
            "p75": round(_video(r.get("video_p75_watched_actions")), 2),
            "p100": round(_video(r.get("video_p100_watched_actions")), 2),
        })

    rows.sort(key=lambda x: (x["date"], x["campaign"], x["adset"], x["ad"]))
    n_days = len({r["date"] for r in rows})
    log(f"Meta: {len(rows)} ad-day rows across {n_days} days")
    return rows


if __name__ == "__main__":
    save_sample("meta", fetch())
