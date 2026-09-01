# How it works — the plain-English version

This is for whoever owns the tracker and needs to understand it well enough to
fix it (with Claude's help) when it breaks. No coding knowledge assumed.

---

## 1. The business picture

Gimi Gimi runs ads on Meta (and later Google). Someone sees an ad, clicks it,
lands on the website, adds a product to cart, starts checkout, and buys. Each
step loses some people — that's "the funnel". The tracker sheet shows how many
people made it through each step each day, and how much the ads cost versus how
much revenue came back.

Words that show up in the sheet:

| Term | In one line |
|---|---|
| **Sessions** | visits to the website |
| **ATC** | "add to cart" — visits where someone put a product in the cart |
| **Checkouts** | visits where someone reached the checkout page |
| **Orders** | actual purchases |
| **Revenue** | money from those orders (can be negative on heavy-refund days) |
| **Spend** | what was paid to the ad platform |
| **ROAS** | revenue ÷ spend. 2.0 means ₹2 back for every ₹1 spent |
| **AOV** | average order value = revenue ÷ orders |
| **CPM** | cost per 1,000 ad views |
| **CTR** | click-through rate = clicks ÷ views |
| **CPC** | cost per click |
| **LPV** | landing page views |
| **Hook rate** | 3-second video views ÷ impressions — did the video grab people |
| **Thruplay %** | how many who started the video basically finished it |

---

## 2. The pipeline as a story

Every morning at 10:45 a timer on GitHub's servers wakes up. It sends two
messengers out: one to Shopify, one to Meta (the Meta one goes through a
service called Composio, which holds the Facebook login so we don't have to
manage a Meta token). Each brings back a table of numbers for the last 35
days. The Meta side has to ask one day at a time, because Meta's tool has no
"give me every day" option — so that step makes about 36 small requests. A checker looks at what came back — are there
roughly 35 days? Any negative spend? Zero everything? If something's off, it
stops here and emails you; the sheet is left alone.

If the numbers look sane, a writer clears the three `RAW_` tabs in the Google
Sheet and types the fresh numbers in. It then reads one cell back from the
Shopify dashboard tab to make sure the sheet's formulas recalculated. Finally
it emails you a short summary. If anything failed anywhere, you get a "FAILED"
email instead, saying which step and what to check.

```
        10:45 AM IST
             |
        [ timer ]  (GitHub Actions)
             |
     +-------+--------+
     |                |
 fetch_shopify    fetch_meta          fetch_gads (does nothing in v1)
     |                |
     +-------+--------+
             |
      [ sanity checks ]  --- if these fail: STOP, email FAILED, sheet untouched
             |
       write_sheets  -> clears & rewrites RAW_Shopify, RAW_Meta, RAW_GAds only
             |
       verify (read one dashboard cell back)
             |
       email_report  -> "OK" email with row counts + yesterday's headline
```

---

## 3. Why the sheet still does the math (and v2 will change that)

There are two kinds of cells in the dashboard:

- **`RAW_` tabs** — plain tables of numbers. The pipeline writes these.
- **Dashboard tabs** (Shopify / Meta Ads / Google Ads) and **`Lists`** — these
  are all *formulas*. They read the `RAW_` tabs and add things up, and the
  Campaign → Ad Set → Ad dropdowns filter them. The pipeline does **not** touch
  these; Google Sheets recalculates them the instant the `RAW_` tabs change.

So in **v1**, "refresh" just means "replace the three `RAW_` tabs". That is
exactly what the old Cowork task did, so the sheet looks and behaves the same.

**v2** plans to also compute the headline totals (the TOTAL rows, ROAS, spend
reconciliation) in Python and write them as fixed numbers, double-checked before
writing — because those are the numbers people act on. The dropdown drill-downs
would stay formula-driven. That work is listed in
`build-prompt-python-tracker.md` and is not done yet.

---

## 4. What each file does

| File | Takes in | Puts out |
|---|---|---|
| `config.py` | — | all the fixed settings: sheet ID, ad account, campaign names, 35-day window, tab names, column order |
| `utils.py` | — | shared helpers: the IST clock, the date window, the `.env` loader, logging |
| `fetch_shopify.py` | Shopify Admin token | one row per day: `date, sessions, atc, checkouts, orders, revenue` |
| `fetch_meta.py` | Composio API key (Composio holds the Facebook login) | one row per ad per day, 20 columns (`date … p100`) |
| `composio_bridge.py` | Composio API key | shared helper: runs one Composio tool, returns its data or a plain-language error |
| `fetch_gads.py` | — | an empty list (v1). Later: Google Ads rows |
| `probe_composio.py` | Composio API key | prints the Meta insights tool schema + a sample response — a setup/debug aid, not part of the daily run |
| `write_sheets.py` | the rows above + the service-account key | the three `RAW_` tabs, cleared and rewritten |
| `email_report.py` | SMTP settings | the daily OK / FAILED email |
| `run_pipeline.py` | — | runs all of the above in order; exits red on failure |
| `.github/workflows/daily-refresh.yml` | — | the 10:45 AM IST timer + the "Run workflow" button |

---

## 5. Where each dashboard number comes from

Every dashboard column is a **sheet formula** reading a `RAW_` tab. The pipeline
only controls the `RAW_` side.

| Dashboard tab | Column | Fed by |
|---|---|---|
| Shopify | Sessions, ATC, Checkouts, Orders, Revenue | `RAW_Shopify` (from `fetch_shopify.py`) |
| Shopify | Spends | `SUMIFS` over `RAW_Meta` for the **four core campaigns** in `config.CORE_META_CAMPAIGNS` + all of `RAW_GAds` (empty in v1) |
| Shopify | ROAS, AOV, A2C %, Checkout %, Checkout→Order % | formulas dividing the columns above |
| Meta Ads | everything | `SUMIFS` / `MAP` over `RAW_Meta` (from `fetch_meta.py`), filtered by the Campaign / Ad Set / Ad dropdowns |
| Google Ads | everything | `RAW_GAds` — empty in v1, so shows 0 / N/A |
| Lists | dropdown options | `UNIQUE` / `FILTER` over `RAW_Meta` and `RAW_GAds` |

Note: the Shopify "Spends" cell counts only the four core campaigns, but the
Meta Ads tab TOTAL counts **all** campaigns — so those two spend figures differ
on purpose (right now by roughly ₹64k, the Awareness + LandingPageViews
campaigns). v2 adds a visible flag for this; v1 leaves it as-is to match today.

---

## 6. What is fragile, and where it lives

| Fragile thing | Where | What happens | Fix |
|---|---|---|---|
| **Access tokens / keys expire or get revoked** | GitHub secrets | "FAILED" email, sheet untouched | regenerate on the platform, update the secret (README step "Rotate") |
| **The Composio connection drops** (someone disconnects Meta Ads, or Composio has an outage) | Composio dashboard | Meta step fails; `TROUBLESHOOTING.md → Composio` | reconnect the Meta Ads toolkit in the Composio dashboard |
| **The Composio SDK changes** (they release often) | `requirements.txt` pins `composio` to `>=0.21,<0.22` | a version bump could change argument or response names | run `python probe_composio.py`, compare, adjust `fetch_meta.py`; or fall back to the direct API path (set `META_ACCESS_TOKEN`, unset `COMPOSIO_API_KEY`) |
| **ShopifyQL analytics access** | `fetch_shopify.py` | Shopify step fails with a GraphQL error | see `TROUBLESHOOTING.md → Shopify analytics`; this is the integration most likely to need a one-off tweak |
| **A platform renames a field** | `fetch_meta.py` (the `actions` mapping) | a column comes through as 0 | update the `action_type` name in `fetch_meta.py` |
| **Core campaign renamed / new one added** | `config.CORE_META_CAMPAIGNS` | Shopify "Spends" silently drops or misses it | add / rename in that list |
| **A `RAW_` tab grows past its row ceiling** | `config.ROW_CEILINGS` + formulas in the sheet | formulas stop reading the extra rows; you get a WARNING in the log first | raise the ceiling in `config.py` **and** widen the ranges in the sheet formulas (`$A$5000` etc.) |
| **A dashboard or RAW tab is renamed** | the Google Sheet | "no tab called ..." failure | rename it back, or update the name in `config.py` |
| **The service account loses sheet access** | Google Sheet share settings | "could not open the sheet" failure | re-share the sheet with the service-account email as Editor |

---

## 7. What to change for common requests

| Request | File | What to change |
|---|---|---|
| "Run at a different time" | `.github/workflows/daily-refresh.yml` | the `cron:` line. It's in **UTC**. IST = UTC + 5:30, so 10:45 IST = `15 5 * * *`. |
| "Use a longer date range" | `config.py` → `WINDOW_DAYS` | raise it — **and** check `ROW_CEILINGS` and the matching `$A$400` / `$A$5000` / `$A$199` ranges in the sheet formulas, or the extra days won't show. |
| "We launched a new core campaign" / "renamed one" | `config.py` → `CORE_META_CAMPAIGNS` | add or rename the exact campaign name. |
| "Send the email to more people" | GitHub secret `EMAIL_TO` | comma-separate the addresses. |
| "A Meta metric is coming through as 0" | `fetch_meta.py` | check the `action_type` name Meta uses now vs. the one in `_pick(...)`. |
| "Add Google Ads" | `fetch_gads.py` (+ a new secret group) | this is the v2 job — implement `fetch()` to return rows keyed by `config.RAW_GADS_COLUMNS`; the rest of the pipeline already handles them. |

---

## 8. Good to know

- The drill-down formulas in the sheet use Google-Sheets-only functions
  (`MAP`, `LAMBDA`, `ARRAYFORMULA`). They work fine in Google Sheets. If the
  sheet is ever downloaded as Excel and re-uploaded, those formulas break —
  don't round-trip it through Excel.
- The pipeline reads `today` in **IST**, not UTC, so the "last day" in the data
  is the correct Indian calendar day.
- Runs and their logs are kept under the repo's **Actions** tab for 90 days.
- **Meta path switch:** `fetch_meta.py` uses Composio when `COMPOSIO_API_KEY`
  is set. If instead `META_ACCESS_TOKEN` is set (and `COMPOSIO_API_KEY` is
  not), it falls back to calling Meta's Marketing API directly in one shot.
  Both paths produce identical rows.
- The git tag **`v0.2.0`** is the version before Composio, when both Shopify
  and Meta used direct APIs — useful reference if the Composio path ever
  needs to be abandoned entirely.
