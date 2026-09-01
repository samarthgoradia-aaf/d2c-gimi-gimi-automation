"""
fetch_gads.py  —  Google Ads.  DEFERRED TO v2.

v1 deliberately ships without Google Ads:
  - the account has had no spend flowing (RAW_GAds is header-only today), and
  - the Google Ads API needs a "developer token" that Google has to approve,
    which can take several days.

Returning an empty list keeps RAW_GAds exactly as it is now (header only).
The dashboard's Google Ads tab already shows 0 / N/A in that state, which is
what the current Cowork output shows too — so nothing changes for the viewer.

When v2 adds Google Ads, this function will return rows keyed by
config.RAW_GADS_COLUMNS and the rest of the pipeline already handles them.
"""
from utils import log


def fetch(token=None):
    log("Google Ads: skipped (not part of v1)")
    return []


if __name__ == "__main__":
    print(fetch())
