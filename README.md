# Gimi Gimi Daily Performance Tracker — automatic refresh

## What this is

Every morning this project pulls the last 35 days of sales numbers from
**Shopify** and ad numbers from **Meta Ads**, and writes them into the
**"Gimi Gimi Daily Performance Tracker"** Google Sheet. The dashboard tabs in
that sheet (Shopify overview, Meta Ads, Google Ads) then recalculate on their
own, exactly as they do today.

It replaces the old setup where a person had to keep the Claude Cowork app open
for the refresh to happen. Now it runs by itself on a schedule, on GitHub's
servers, with no app and no computer needing to be on.

- **Live sheet:** https://docs.google.com/spreadsheets/d/1-v-zWqlLKVHJlL7X2hIfaxmVDl21VtZI1gOhJDd40sg/edit
- **When it runs:** every day at **10:45 AM IST**.
- **What you get:** one email every day — either "OK" with the row counts and
  yesterday's headline numbers, or "FAILED" with a plain explanation of what
  broke and which file to look at.

> **v1 scope.** This version only refreshes the three `RAW_` tabs, just like the
> old Cowork task did. It does **not** yet include Google Ads (the account has
> no spend flowing and its API needs a slow approval) and it does **not** yet
> compute any dashboard cells in Python — the sheet's own formulas still do
> that. Those are planned for v2. See `HOW-IT-WORKS.md`.

---

## How it's put together

```
run_pipeline.py         the conductor — the daily schedule runs this
  ├── fetch_shopify.py   two ShopifyQL queries  -> daily sales/traffic rows
  ├── fetch_meta.py      Meta Marketing API     -> one row per ad per day
  ├── fetch_gads.py      Google Ads             -> nothing yet (v2)
  ├── write_sheets.py    clears + rewrites RAW_Shopify / RAW_Meta / RAW_GAds
  └── email_report.py    sends the daily OK / FAILED email

config.py               all the non-secret settings (IDs, campaign names, window)
.github/workflows/daily-refresh.yml   the timer
```

Nothing else in the sheet is touched. The dashboard tabs and the `Lists` tab
keep their formulas and dropdowns and recalculate automatically.

---

## One-time setup

You need four things. **None of them ever go into the code.** For testing they
go in a local file called `.env`; for the daily run they go into GitHub's
encrypted secret store. The names are the same in both places.

> ⚠️ **If any of these values is ever pasted into a chat, an email, a Slack
> message, or committed to the repo by accident — regenerate it immediately on
> the platform it came from.** Each one can spend money or read customer data.

### 1. Google Sheets access (a "service account")

A service account is a robot Google account the script logs in as.

1. Go to <https://console.cloud.google.com/> and create a project (any name).
2. In **APIs & Services → Library**, search **Google Sheets API** and click
   **Enable**.
3. In **APIs & Services → Credentials → Create credentials → Service account**.
   Give it a name, click through, **Done**.
4. Click the new service account → **Keys** tab → **Add key → Create new key →
   JSON**. A `.json` file downloads. **This file is a password. Keep it safe.**
5. Open that file, copy the `client_email` value (looks like
   `something@your-project.iam.gserviceaccount.com`).
6. Open the Google Sheet → **Share** → paste that email → give it **Editor** →
   send.
7. The whole contents of the `.json` file is the value of the
   `GOOGLE_SERVICE_ACCOUNT_JSON` secret (see below).

### 2. Shopify Admin API token

1. Shopify admin → **Settings → Apps and sales channels → Develop apps**.
2. **Create an app** (name it e.g. "Tracker refresh").
3. **Configure Admin API scopes** → tick **`read_reports`**, **`read_orders`**,
   **`read_analytics`** → **Save**.
4. **Install app** → then **Reveal token once** and copy the **Admin API access
   token** (starts with `shpat_`). That is `SHOPIFY_ADMIN_TOKEN`.

### 3. Meta (Facebook) access token

1. <https://business.facebook.com/> → **Business settings → Users → System
   users**.
2. **Add** a system user (name e.g. "Tracker"), role **Admin** or **Employee**.
3. **Add assets** → **Ad accounts** → select the Gimi Gimi ad account
   (`act_868396352281563`) → give **View performance** (read) access.
4. **Generate new token** → pick the app → tick **`ads_read`** → generate.
   Set expiry to **Never** if offered. That is `META_ACCESS_TOKEN`.

### 4. Email sending (SMTP)

Easiest is a Gmail (or Google Workspace) account with an **App Password**:

1. That account → **Google Account → Security → 2-Step Verification** (must be
   on) → **App passwords** → create one, name it "Tracker".
2. Use these values:
   - `SMTP_HOST` = `smtp.gmail.com`
   - `SMTP_PORT` = `587`
   - `SMTP_USER` = the full gmail address
   - `SMTP_PASSWORD` = the 16-character app password (no spaces)
   - `EMAIL_FROM` = the same gmail address
   - `EMAIL_TO` = `parth@mealofthemoment.com` (comma-separate for more than one)

If email isn't set up yet, the pipeline still runs — it just prints the summary
into the run log instead of emailing it.

---

## Putting the secrets into GitHub (for the daily run)

Repo → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**, once per name:

| Secret name | Value |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | the entire contents of the service-account `.json` file |
| `SHOPIFY_ADMIN_TOKEN` | the `shpat_...` token |
| `META_ACCESS_TOKEN` | the Meta system-user token |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | sending gmail address |
| `SMTP_PASSWORD` | the app password |
| `EMAIL_FROM` | sending gmail address |
| `EMAIL_TO` | `parth@mealofthemoment.com` |

**To rotate any of them later:** regenerate the value on the platform, then edit
the matching secret here. Nothing in the code changes.

---

## Running it manually to test

**On GitHub (recommended first test):** repo → **Actions** → **Daily tracker
refresh** → **Run workflow**. Watch the log; you should get an email at the end.

**On your own computer:**

```bash
pip install -r requirements.txt
cp .env.example .env          # then edit .env with the real values
python fetch_shopify.py       # test one source at a time first
python fetch_meta.py
python run_pipeline.py        # the whole thing
```

`fetch_*.py` scripts save what they got to `data/` so you can inspect it.
`.env` and `data/` are git-ignored and will not be committed.

---

## When something looks wrong

Open **`TROUBLESHOOTING.md`**. It lists every error message the pipeline can
print, what it means, and what to do — including a line you can copy straight
into Claude to get help.
