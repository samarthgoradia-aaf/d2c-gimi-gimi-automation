"""
run_pipeline.py  —  the conductor. This is the file the daily schedule runs.

Order:
  1. fetch Shopify, Meta, Google Ads (Google Ads is a no-op in v1)
  2. basic checks on what came back
  3. write the RAW tabs
  4. read back one dashboard cell to confirm the formulas recalculated
  5. email a summary (on success AND failure)

Exit code is non-zero on any failure so GitHub Actions marks the run red.

SHOPIFY-ONLY MODE
  If Meta is not set up yet (no COMPOSIO_API_KEY and no META_ACCESS_TOKEN), or
  if you set SKIP_META=1, the pipeline still runs: it refreshes RAW_Shopify and
  leaves RAW_Meta completely untouched. Useful to get the Shopify half running
  on the schedule while the Meta connection is still being sorted out.
"""
import os
import sys
import traceback

import config
import email_report
import fetch_gads
import fetch_meta
import fetch_shopify
import write_sheets
from utils import PipelineError, date_window, log, save_sample


def _meta_enabled():
    if os.environ.get("SKIP_META", "").strip() in ("1", "true", "yes"):
        return False
    return bool(
        os.environ.get("COMPOSIO_API_KEY", "").strip()
        or os.environ.get("META_ACCESS_TOKEN", "").strip()
    )


def _checks(shopify_rows, meta_rows):
    """Cheap sanity checks. If any fail we do NOT write to the sheet."""
    if len(shopify_rows) < config.WINDOW_DAYS - 5:
        raise PipelineError(
            f"Shopify returned only {len(shopify_rows)} days; expected about "
            f"{config.WINDOW_DAYS + 1}. Not writing to the sheet. See "
            "TROUBLESHOOTING.md -> 'Shopify empty'."
        )

    if meta_rows is None:
        return  # Shopify-only mode

    meta_days = len({r["date"] for r in meta_rows})
    if meta_days < config.WINDOW_DAYS - 7:
        raise PipelineError(
            f"Meta returned only {meta_days} distinct days; expected about "
            f"{config.WINDOW_DAYS + 1}. Not writing to the sheet. See "
            "TROUBLESHOOTING.md -> 'Meta empty'."
        )

    neg = [r for r in meta_rows if r["spend"] < 0]
    if neg:
        r = neg[0]
        raise PipelineError(
            f"A Meta row has negative spend ({r['campaign']} on {r['date']}, "
            f"spend {r['spend']}). That should never happen. Not writing."
        )

    if sum(r["spend"] for r in meta_rows) <= 0:
        raise PipelineError(
            "Total Meta spend across the whole window is zero. Something is "
            "wrong with the fetch. Not writing. See TROUBLESHOOTING.md -> "
            "'Meta empty'."
        )


def _run():
    since, until = date_window()
    meta_on = _meta_enabled()
    log(f"=== Gimi Gimi tracker refresh:  {since} .. {until} ===")
    if not meta_on:
        log("Meta is OFF for this run (no Composio/Meta credentials, or "
            "SKIP_META set). RAW_Meta will be left untouched.")

    log("Step 1: fetch Shopify")
    shopify_rows = fetch_shopify.fetch()
    save_sample("shopify", shopify_rows)

    meta_rows = None
    if meta_on:
        log("Step 2: fetch Meta")
        meta_rows = fetch_meta.fetch()
        save_sample("meta", meta_rows)

    log("Step 3: fetch Google Ads")
    gads_rows = fetch_gads.fetch()

    _checks(shopify_rows, meta_rows)

    log("Step 4: write RAW tabs")
    sh = write_sheets.write_all(shopify_rows, meta_rows, gads_rows)
    write_sheets.verify(sh)

    counts = {config.RAW_SHOPIFY_TAB: len(shopify_rows)}
    if meta_rows is not None:
        counts[config.RAW_META_TAB] = len(meta_rows)
    else:
        counts[config.RAW_META_TAB] = "left unchanged (Meta off)"
    counts[config.RAW_GADS_TAB] = len(gads_rows)
    return since, until, counts, shopify_rows, meta_rows


def main():
    try:
        since, until, counts, shopify_rows, meta_rows = _run()
    except PipelineError as e:
        log(f"FAILED: {e}")
        email_report.send_failure(str(e), traceback.format_exc())
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 - last-resort catch for anything else
        log(f"FAILED (unexpected): {e}")
        email_report.send_failure(f"Unexpected error: {e}", traceback.format_exc())
        sys.exit(1)

    email_report.send_success(since, until, counts, shopify_rows, meta_rows)
    log("=== done ===")


if __name__ == "__main__":
    main()
