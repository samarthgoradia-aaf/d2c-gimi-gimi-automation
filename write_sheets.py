"""
write_sheets.py  —  writes the three RAW_ tabs into the Google Sheet.

What it touches:  RAW_Shopify, RAW_Meta, RAW_GAds  (data only, below the header).
What it does NOT touch:  the Shopify / Meta Ads / Google Ads dashboard tabs and
the Lists tab. Those are all formulas and recalculate on their own once the
RAW tabs change.

Safety model:
  * All data is fetched and sanity-checked in run_pipeline.py BEFORE this runs.
  * Per tab: make sure it has enough rows -> clear the old data below row 1 ->
    write header + new rows in chunks.
  * A tab is never cleared until its replacement values are in hand.
"""
import json
import os

import gspread
from google.oauth2.service_account import Credentials

import config
from utils import PipelineError, log

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_CHUNK_ROWS = 500


def _client():
    raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            raise PipelineError(
                "GOOGLE_SERVICE_ACCOUNT_JSON is set but is not valid JSON. It "
                "must be the whole key file contents on one line. See "
                "TROUBLESHOOTING.md -> 'Google Sheet access'."
            )
        creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
    else:
        path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
        if not path or not os.path.exists(path):
            raise PipelineError(
                "No Google service-account credentials found. Set "
                "GOOGLE_SERVICE_ACCOUNT_JSON (whole key file on one line) or "
                "GOOGLE_SERVICE_ACCOUNT_FILE (path to it). See README.md -> "
                "'Google Sheets access'."
            )
        creds = Credentials.from_service_account_file(path, scopes=_SCOPES)
    return gspread.authorize(creds)


def _open_sheet():
    try:
        return _client().open_by_key(config.SPREADSHEET_ID)
    except gspread.SpreadsheetNotFound:
        raise PipelineError(
            "Could not open the Google Sheet. Either the SPREADSHEET_ID in "
            "config.py is wrong, or the sheet has not been shared with the "
            "service account's email address (as Editor). See README.md -> "
            "'Google Sheets access'."
        )
    except gspread.exceptions.APIError as e:
        raise PipelineError(
            f"Google Sheets API error opening the sheet: {e}. The service "
            "account may not have edit access. See TROUBLESHOOTING.md -> "
            "'Google Sheet access'."
        )


def _col_letter(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _write_tab(sh, tab, columns, rows):
    try:
        ws = sh.worksheet(tab)
    except gspread.WorksheetNotFound:
        raise PipelineError(
            f"The sheet has no tab called '{tab}'. Was it renamed? The tab "
            "names live in config.py. See TROUBLESHOOTING.md -> 'Tab renamed'."
        )

    ceiling = config.ROW_CEILINGS.get(tab)
    if ceiling and (len(rows) + 1) > ceiling * 0.8:
        log(f"WARNING: {tab} now has {len(rows)} data rows; the dashboard "
            f"formulas stop at row {ceiling}. Approaching the limit.")

    # Grow the tab if needed; never shrink below the documented ceiling.
    target_rows = max(ws.row_count, ceiling or 0, len(rows) + 1)
    if ws.row_count < target_rows or ws.col_count < len(columns):
        ws.resize(rows=target_rows, cols=max(ws.col_count, len(columns)))

    last_col = _col_letter(len(columns))

    # Clear old data (keep row 1 so formatting on the header stays).
    ws.batch_clear([f"A2:{last_col}{ws.row_count}"])

    matrix = [columns] + [[r.get(c, "") for c in columns] for r in rows]
    for i in range(0, len(matrix), _CHUNK_ROWS):
        chunk = matrix[i:i + _CHUNK_ROWS]
        first = i + 1
        last = i + len(chunk)
        ws.update(
            range_name=f"A{first}:{last_col}{last}",
            values=chunk,
            value_input_option="USER_ENTERED",
        )
    log(f"{tab}: wrote {len(rows)} data rows")


def write_all(shopify_rows, meta_rows, gads_rows):
    """Write all three RAW tabs. Returns the open Spreadsheet for verify()."""
    sh = _open_sheet()
    _write_tab(sh, config.RAW_SHOPIFY_TAB, config.RAW_SHOPIFY_COLUMNS, shopify_rows)
    _write_tab(sh, config.RAW_META_TAB, config.RAW_META_COLUMNS, meta_rows)
    _write_tab(sh, config.RAW_GADS_TAB, config.RAW_GADS_COLUMNS, gads_rows)
    return sh


def verify(sh):
    """
    Cheap read-back check: after the RAW tabs change, the Shopify overview
    TOTAL row (B6:G6) should recalculate to non-empty numbers.
    """
    try:
        ws = sh.worksheet("Shopify")
    except gspread.WorksheetNotFound:
        raise PipelineError(
            "The 'Shopify' dashboard tab is missing — cannot verify the write."
        )
    total = ws.get("B6:G6")
    flat = total[0] if total else []
    if not flat or all(str(x).strip() == "" for x in flat):
        raise PipelineError(
            "The RAW tabs were written but the Shopify overview 'TOTAL' row "
            "(B6:G6) is empty. The dashboard formulas may be broken. See "
            "TROUBLESHOOTING.md -> 'Dashboard blank'."
        )
    log(f"verify: Shopify!B6:G6 = {flat}")
