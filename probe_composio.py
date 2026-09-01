"""
probe_composio.py  —  one-off helper to lock down the Composio tool details.

Run this once, after COMPOSIO_API_KEY is set and the Meta Ads toolkit is
connected in the Composio dashboard:

    python probe_composio.py

It prints:
  1. the exact input schema of METAADS_GET_INSIGHTS (so the argument names in
     fetch_meta.py can be confirmed / corrected), and
  2. the result of a tiny 1-day insights call, so we can see the real response
     shape and the pagination fields.

Nothing here writes to the Google Sheet.
"""
import json

import config
from composio_bridge import execute, tool_schema, user_id
from utils import date_window, log


def main():
    log(f"Composio user_id: {user_id()}")

    print("\n=== METAADS_GET_INSIGHTS input schema ===")
    try:
        schema = tool_schema("METAADS_GET_INSIGHTS")
        print(json.dumps(schema, indent=2, default=str)[:6000])
    except Exception as e:  # noqa: BLE001
        print(f"(could not fetch schema: {e})")

    since, until = date_window()
    print(f"\n=== sample call: 1 day ({until}) at ad level ===")
    args = {
        "object_id": config.META_AD_ACCOUNT_ID,
        "level": "ad",
        "time_range": {"since": until, "until": until},
        "fields": [
            "campaign_name", "adset_name", "ad_name", "spend", "impressions",
            "actions", "action_values",
        ],
        "filtering": [
            {"field": "campaign.name", "operator": "CONTAIN", "value": "GG_"},
        ],
        "limit": 25,
    }
    print("arguments sent:")
    print(json.dumps(args, indent=2))
    data = execute("METAADS_GET_INSIGHTS", args)
    print("\nresponse data (first 6000 chars):")
    print(json.dumps(data, indent=2, default=str)[:6000])


if __name__ == "__main__":
    main()
