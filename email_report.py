"""
email_report.py  —  sends the daily summary email (success or failure) by SMTP.

Defaults to Gmail's SMTP server. The sending account needs an "App Password"
(Google Account -> Security -> 2-Step Verification -> App passwords); a normal
account password will not work.

If the SMTP settings are not all filled in, the summary is printed to the log
instead of emailed, so the pipeline still works while email is being set up.
"""
import os
import smtplib
from email.message import EmailMessage

import config
from utils import ist_now, log


def _cfg():
    user = os.environ.get("SMTP_USER", "").strip()
    return {
        "host": os.environ.get("SMTP_HOST", "smtp.gmail.com").strip(),
        "port": int(os.environ.get("SMTP_PORT", "587").strip() or "587"),
        "user": user,
        "password": os.environ.get("SMTP_PASSWORD", "").strip(),
        "sender": os.environ.get("EMAIL_FROM", "").strip() or user,
        "to": [x.strip() for x in os.environ.get("EMAIL_TO", "").split(",") if x.strip()],
    }


def _send(subject, body):
    c = _cfg()
    if not (c["user"] and c["password"] and c["to"]):
        log("email: SMTP not fully configured - printing summary instead:")
        log(f"\n--- {subject} ---\n{body}\n---")
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = c["sender"]
    msg["To"] = ", ".join(c["to"])
    msg.set_content(body)
    try:
        with smtplib.SMTP(c["host"], c["port"], timeout=30) as s:
            s.starttls()
            s.login(c["user"], c["password"])
            s.send_message(msg)
        log(f"email: sent '{subject}' to {c['to']}")
    except Exception as e:  # noqa: BLE001 - email must never crash the run
        log(f"email: FAILED to send ({e}). Summary was:\n{body}")


def _sum_spend(meta_rows, date, campaigns=None):
    return sum(
        r["spend"] for r in meta_rows
        if r["date"] == date and (campaigns is None or r["campaign"] in campaigns)
    )


def _yesterday_line(shopify_rows, meta_rows):
    if not shopify_rows:
        return "n/a"
    last = shopify_rows[-1]
    d = last["date"]
    if meta_rows is None:
        return (
            f"{d}:  revenue Rs {last['revenue']:,.0f}  |  "
            f"orders {int(last['orders'])}  |  sessions {int(last['sessions'])}  "
            f"(Meta not refreshed this run)"
        )
    core = _sum_spend(meta_rows, d, config.CORE_META_CAMPAIGNS)
    all_meta = _sum_spend(meta_rows, d)
    rev = last["revenue"]
    roas = (rev / core) if core else 0.0
    return (
        f"{d}:  revenue Rs {rev:,.0f}  |  orders {int(last['orders'])}  |  "
        f"core Meta spend Rs {core:,.0f}  |  all Meta spend Rs {all_meta:,.0f}  |  "
        f"blended ROAS {roas:.2f}"
    )


def _sheet_url():
    return f"https://docs.google.com/spreadsheets/d/{config.SPREADSHEET_ID}/edit"


def send_success(since, until, counts, shopify_rows, meta_rows):
    lines = [
        f"Gimi Gimi tracker refreshed OK at {ist_now():%Y-%m-%d %H:%M} IST.",
        "",
        f"Window rebuilt: {since}  to  {until}",
        "",
        "Rows written:",
    ]
    lines += [f"  {k}: {v}" for k, v in counts.items()]
    lines += [
        "",
        "Latest day in the data:",
        f"  {_yesterday_line(shopify_rows, meta_rows)}",
        "",
        f"Sheet: {_sheet_url()}",
    ]
    _send(f"[Gimi Gimi Tracker] OK - {until}", "\n".join(lines))


def send_failure(summary, detail):
    body = "\n".join([
        f"Gimi Gimi tracker FAILED at {ist_now():%Y-%m-%d %H:%M} IST.",
        "",
        "What happened:",
        f"  {summary}",
        "",
        "If this happened while fetching data, the Google Sheet was NOT changed.",
        "",
        f"Sheet: {_sheet_url()}",
        "",
        "Technical detail (paste this to Claude if you need help):",
        detail or "(none)",
    ])
    _send(f"[Gimi Gimi Tracker] FAILED - {ist_now():%Y-%m-%d}", body)
