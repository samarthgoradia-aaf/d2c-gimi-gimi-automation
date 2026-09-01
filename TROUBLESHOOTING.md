# Troubleshooting — what to do when it breaks

Find the section that matches the email or the error in the run log. Each entry
ends with a line you can **paste straight into Claude** to get help fixing it.

Where to see the error in full: repo → **Actions** tab → click the red run →
click the **Run the pipeline** step.

---

## 0. The sheet did not update at all today

1. Repo → **Actions**. Is there a run for today?
   - **No run at all** → GitHub may have paused scheduled runs (it does this
     after ~60 days of no activity in the repo, and sometimes on its own).
     Open the workflow and click **Enable workflow** / push any small change,
     then **Run workflow** by hand.
   - **A red run** → open it, read the failing step, jump to the matching
     section below.
   - **A green run but the sheet looks stale** → check you're looking at the
     right sheet (ID in `config.py`) and the right tabs; the RAW tabs update,
     the dashboard recalculates from them.
2. Did you get **any** email? If not, see section 7.

> Paste this into Claude: *"My Gimi Gimi tracker didn't refresh the Google Sheet
> today. Here's the GitHub Actions run log: [paste]. What went wrong and how do
> I fix it?"*

---

## 1. Shopify token — "Shopify rejected the Admin API token (401 Unauthorized)"

The `SHOPIFY_ADMIN_TOKEN` is wrong, was regenerated, or the app was
uninstalled.

**Fix:** Shopify admin → Settings → Apps and sales channels → Develop apps →
your app → **API credentials**. If needed, uninstall + reinstall to get a fresh
**Admin API access token** (`shpat_...`). Update the `SHOPIFY_ADMIN_TOKEN`
secret in GitHub (repo → Settings → Secrets and variables → Actions).

> Paste this into Claude: *"My Gimi Gimi pipeline failed with 'Shopify rejected
> the Admin API token'. The relevant file is fetch_shopify.py. Here it is:
> [paste]. Walk me through regenerating and updating the token."*

---

## 2. Shopify analytics — "Shopify GraphQL error" / "returned no analytics table"

The token works, but the analytics query (ShopifyQL) didn't run. Usual causes:

- the app is missing the **`read_reports`** scope → add it in the app's Admin
  API scopes, save, reinstall;
- the store's plan or settings don't expose ShopifyQL over the Admin API, or
  the API version in `config.py` (`SHOPIFY_API_VERSION`) no longer supports the
  `shopifyqlQuery` field.

This is the part of the pipeline most likely to need a one-time code change, so
if the scope is definitely present, get Claude to adjust the query.

> Paste this into Claude: *"My Gimi Gimi pipeline failed fetching Shopify with
> this error: [paste]. The file is fetch_shopify.py: [paste]. The Shopify app
> has the read_reports scope. Is the ShopifyQL query or API version wrong, and
> what should it be instead?"*

---

## 3. Shopify empty — "Shopify returned zero days" / "only N days"

The query ran but came back with little or nothing. Could be a genuine gap
(store was closed / no traffic — unlikely for 35 days) or the date handling is
off.

**Check:** open `data/shopify.json` from a local run (`python fetch_shopify.py`)
and see what actually came back.

> Paste this into Claude: *"My Gimi Gimi Shopify fetch returned too few days.
> Here's data/shopify.json: [paste] and fetch_shopify.py: [paste]. What's
> wrong?"*

---

## 4. Meta token — "Meta rejected the access token"

`META_ACCESS_TOKEN` expired, was revoked, or lost `ads_read` / access to the ad
account.

**Fix:** business.facebook.com → Business settings → Users → System users →
your system user → confirm the Gimi Gimi ad account is still assigned with at
least read access → **Generate new token** with `ads_read` (expiry: Never).
Update the `META_ACCESS_TOKEN` secret in GitHub.

> Paste this into Claude: *"My Gimi Gimi pipeline failed with 'Meta rejected the
> access token'. Here's fetch_meta.py: [paste]. Walk me through minting a new
> non-expiring system-user token and updating the GitHub secret."*

---

## 5. Meta empty — "Meta returned zero ad rows" / "only N distinct days" / "total spend is zero"

The call worked but returned nothing useful. Causes: no spend in the window
(unlikely), the token can see the app but not this ad account, or the campaign
filter (`CONTAIN "GG_"`) matched nothing because campaigns were renamed off the
`GG_` prefix.

**Check:** `python fetch_meta.py` locally, look at `data/meta.json`.

> Paste this into Claude: *"My Gimi Gimi Meta fetch came back empty/too small.
> Here's fetch_meta.py: [paste] and the first part of data/meta.json: [paste].
> Is it the filter, the account access, or the date range?"*

---

## 6. Google Sheet access

**"No Google service-account credentials found"** — the
`GOOGLE_SERVICE_ACCOUNT_JSON` secret is missing or empty. Re-add it: the value
is the **entire** contents of the service-account `.json` key file.

**"GOOGLE_SERVICE_ACCOUNT_JSON is set but is not valid JSON"** — it got
truncated or mangled when pasted. Paste the whole file again, exactly.

**"Could not open the Google Sheet"** — the sheet isn't shared with the service
account. Open the `.json` file, copy `client_email`, share the sheet with that
address as **Editor**.

**"Google Sheets API error opening the sheet"** — usually the Sheets API isn't
enabled on the Google Cloud project. Console → APIs & Services → Library →
Google Sheets API → **Enable**.

> Paste this into Claude: *"My Gimi Gimi pipeline failed writing to Google
> Sheets with: [paste]. Here's write_sheets.py: [paste] and README section
> 'Google Sheets access'. What do I fix?"*

---

## 7. Tab renamed — "The sheet has no tab called 'RAW_Meta'" (or similar)

A tab was renamed or deleted in the Google Sheet. Either rename it back to the
exact name, or update the matching name near the top of `config.py`
(`RAW_SHOPIFY_TAB`, `RAW_META_TAB`, `RAW_GADS_TAB`).

> Paste this into Claude: *"My Gimi Gimi pipeline says a tab is missing: [paste
> error]. Here's config.py: [paste]. How do I point it at the right tab?"*

---

## 8. Dashboard blank — "the Shopify overview 'TOTAL' row (B6:G6) is empty"

The RAW tabs were written but the dashboard didn't recalculate to numbers.
Likely a formula on the **Shopify** tab was edited or deleted, or a `RAW_` tab's
**column order** changed (the formulas read columns by position — see
`config.RAW_*_COLUMNS` for the correct order).

**Check:** open the Shopify tab, click `B6`, confirm there's a `SUMIFS`
formula. Compare `RAW_Meta` / `RAW_Shopify` header rows against
`config.py`.

> Paste this into Claude: *"My Gimi Gimi pipeline wrote the RAW tabs but says
> the dashboard TOTAL row is empty. Here's config.py: [paste]. What should I
> check in the sheet?"*

---

## 9. A whole dashboard column is empty or zero

- **Google Ads tab is all 0 / N/A** — expected in v1. Google Ads isn't
  connected yet.
- **One Meta column (e.g. Checkouts, LPV) is 0 everywhere** — Meta probably
  renamed that `action_type`. Fix the name in `fetch_meta.py` (`_pick(...)`).
- **Spend looks far too low / ROAS impossibly high on the Shopify tab** — a
  core campaign was renamed and dropped out of `config.CORE_META_CAMPAIGNS`.
  Add the new name.

> Paste this into Claude: *"On my Gimi Gimi sheet the [column name] column is
> zero/blank. Here's fetch_meta.py: [paste] and config.py: [paste]. Which
> mapping is wrong?"*

---

## 10. No email arrived

The pipeline only emails if `SMTP_USER`, `SMTP_PASSWORD` and `EMAIL_TO` are all
set. If they're not, it prints the summary into the run log instead — check
**Actions → the run → Run the pipeline**.

If they are set and mail still isn't arriving:
- Gmail app password wrong or 2-Step Verification off on that account →
  regenerate the app password.
- Check spam.
- The log will show `email: FAILED to send (...)` with the reason.

> Paste this into Claude: *"My Gimi Gimi pipeline ran but no email came. Here's
> the end of the run log: [paste] and email_report.py: [paste]. What's wrong
> with the SMTP setup?"*

---

## 11. The run is red but I can't tell why

Open the run, expand every step, copy the **last 30–40 lines** of output.

> Paste this into Claude: *"My Gimi Gimi tracker GitHub Actions run failed.
> Here's the tail of the log: [paste]. Here are the files it mentions: [paste].
> What broke and what's the fix?"*
