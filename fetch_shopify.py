"""
fetch_shopify.py  —  gets raw Shopify numbers.

Runs two ShopifyQL analytics queries (one for traffic, one for sales) over the
last WINDOW_DAYS and merges them by date.

OUT: a list of dicts, one per day, with keys:
     date, sessions, atc, checkouts, orders, revenue

Run it on its own to test the connection and save a sample:
     python fetch_shopify.py
"""
import json

import requests

import config
from utils import PipelineError, require_env, date_window, log, save_sample

_GRAPHQL_URL = (
    f"https://{config.SHOPIFY_STORE_DOMAIN}"
    f"/admin/api/{config.SHOPIFY_API_VERSION}/graphql.json"
)

# ShopifyQL is run through the GraphQL Admin API's shopifyqlQuery field.
_GQL = """
query ShopifyQL($q: String!) {
  shopifyqlQuery(query: $q) {
    __typename
    ... on TableResponse {
      tableData { rowData columns { name } }
    }
    parseErrors { code message }
  }
}
"""

_SESSIONS_QL = (
    "FROM sessions "
    "SHOW sessions, sessions_with_cart_additions, sessions_that_reached_checkout "
    "TIMESERIES day SINCE {since} UNTIL {until}"
)
_SALES_QL = (
    "FROM sales SHOW orders, total_sales "
    "TIMESERIES day SINCE {since} UNTIL {until}"
)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _run_ql(token, ql):
    """Run one ShopifyQL string, return a list of {column: value} dicts."""
    resp = requests.post(
        _GRAPHQL_URL,
        headers={
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
        },
        json={"query": _GQL, "variables": {"q": ql}},
        timeout=60,
    )
    if resp.status_code == 401:
        raise PipelineError(
            "Shopify rejected the Admin API token (401 Unauthorized). The "
            "token is wrong or was revoked. See TROUBLESHOOTING.md -> "
            "'Shopify token'."
        )
    if resp.status_code != 200:
        raise PipelineError(
            f"Shopify API returned HTTP {resp.status_code}. First part of the "
            f"response: {resp.text[:500]}"
        )

    body = resp.json()
    if body.get("errors"):
        raise PipelineError(
            "Shopify GraphQL error while running an analytics query: "
            f"{json.dumps(body['errors'])[:500]}. The app may be missing the "
            "'read_reports' scope, or ShopifyQL analytics is not available for "
            "this store. See TROUBLESHOOTING.md -> 'Shopify analytics'."
        )

    node = (body.get("data") or {}).get("shopifyqlQuery") or {}
    if node.get("parseErrors"):
        raise PipelineError(
            "Shopify could not understand an analytics query (this is a bug in "
            f"the query text, not your setup): {json.dumps(node['parseErrors'])[:500]}"
        )

    table = node.get("tableData")
    if not table or not table.get("columns"):
        raise PipelineError(
            "Shopify returned no analytics table. Response type was "
            f"'{node.get('__typename')}'. See TROUBLESHOOTING.md -> "
            "'Shopify analytics'."
        )

    cols = [c["name"] for c in table["columns"]]
    return [dict(zip(cols, row)) for row in (table.get("rowData") or [])]


def _row_date(row):
    """Pull the date out of a ShopifyQL row (it sits under the 'day' column)."""
    if "day" in row:
        return str(row["day"])[:10]
    for v in row.values():
        s = str(v)
        if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-":
            return s[:10]
    raise PipelineError(f"Shopify analytics row had no recognisable date: {row}")


def _blank(d):
    return {
        "date": d, "sessions": 0.0, "atc": 0.0, "checkouts": 0.0,
        "orders": 0.0, "revenue": 0.0,
    }


def fetch(token=None):
    token = token or require_env("SHOPIFY_ADMIN_TOKEN")
    since, until = date_window()
    log(f"Shopify: requesting {since} .. {until}")

    sessions_rows = _run_ql(token, _SESSIONS_QL.format(since=since, until=until))
    sales_rows = _run_ql(token, _SALES_QL.format(since=since, until=until))

    by_date = {}
    for r in sessions_rows:
        d = _row_date(r)
        by_date.setdefault(d, _blank(d))
        by_date[d]["sessions"] = _num(r.get("sessions"))
        by_date[d]["atc"] = _num(r.get("sessions_with_cart_additions"))
        by_date[d]["checkouts"] = _num(r.get("sessions_that_reached_checkout"))
    for r in sales_rows:
        d = _row_date(r)
        by_date.setdefault(d, _blank(d))
        by_date[d]["orders"] = _num(r.get("orders"))
        by_date[d]["revenue"] = _num(r.get("total_sales"))  # can be negative

    rows = [by_date[d] for d in sorted(by_date)]
    if not rows:
        raise PipelineError(
            f"Shopify returned zero days for the last {config.WINDOW_DAYS} "
            f"days. See TROUBLESHOOTING.md -> 'Shopify empty'."
        )
    log(f"Shopify: {len(rows)} day rows")
    return rows


if __name__ == "__main__":
    save_sample("shopify", fetch())
