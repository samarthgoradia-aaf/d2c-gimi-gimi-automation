# BUILD PROMPT — Gimi Gimi Daily Performance Tracker (Python Pipeline, Claude-Free Runtime)

> **Purpose:** replace the Cowork-agent daily refresh described in
> `rebuild-prompt-gimi-gimi-tracker.md` (same directory) with a plain Python
> pipeline that runs on a schedule with zero AI involvement at execution time.
> Claude is used only to build and occasionally repair this pipeline, never to
> run it day to day.

> **CRITICAL CONTEXT ABOUT THE AUDIENCE — read this before anything else.**
> This is being built by someone with limited coding experience, and handed
> over to someone with none at all. The person who inherits this will need to
> diagnose and fix breakages themselves, by reading the docs and pasting the
> relevant part into Claude. That means:
> - Every document you write assumes zero prior knowledge. No unexplained
>   jargon. If a technical term is unavoidable, define it in plain words the
>   first time it appears.
> - Every error the pipeline can produce must be written in human language,
>   not a raw stack trace, and must say what to check and where.
> - The docs are as much a deliverable as the code. A working script with
>   docs the owner cannot follow is a failed build.
> Do not skip or shorten the documentation phase. It is Phase 6 and it is
> mandatory.

---

## STEP 0 — READ FIRST

Read `rebuild-prompt-gimi-gimi-tracker.md` in this directory before writing
any code. It is the source of truth for:
- exact field lists and column order for Shopify, Meta, Google Ads
- the `action_type` mapping for Meta (LPV, ATC, Checkout, Purchases, Revenue,
  video metrics) and all fallback field names
- the four Meta campaign names used in the spend rollup
  (`GG_Sales_Catalog_Tier2`, `GG_Sales_Media_Tier2`,
  `GG_Sales_Media_FocusCities`, `GG_Sales_Catalog_FocusCities`)
- every formula currently in the sheet (ROAS, CPM, CTR, CPC, hook rate,
  thruplay %, funnel %, AOV)
- the known limitations and pitfalls section. Do not silently re-introduce
  bugs already documented there (non-additive reach/frequency, GAQL is not
  SQL, Meta response written to file rather than returned inline, pagination
  required).

Do not improvise metric definitions. If a formula in that doc is ambiguous,
stop and ask rather than guessing.

---

## THE ARCHITECTURE DECISION (already made — build this way)

This is a **hybrid**. Two kinds of output go into the same spreadsheet, for
two different reasons:

**1. Headline numbers → computed in Python, written as static values.**
The daily overview (sessions, ATC, checkouts, orders, revenue, spend, ROAS,
AOV, funnel percentages) and the Meta / Google Ads summary rows. These are
what someone glances at each morning to make an ad-spend decision. They must
be verified before they are written, because a wrong headline number gets
acted on and nobody notices it was wrong. No formulas on the sheet side for
these.

**2. Drill-down views → raw data tab plus the existing Sheets formulas.**
Python writes clean raw rows (one per ad per day) into the RAW_ tabs. The
existing dropdown-driven filtering (Campaign → Ad Set → Ad cascade, the
`Lists` tab, the SUMIFS/MAP/ARRAYFORMULA views) stays exactly as it is today
and keeps working. If a filtered view breaks, someone is actively looking at
it and will notice. That is an acceptable risk for the detail views; it is not
acceptable for the headline numbers.

Do not remove the interactive filtering. Do not convert the drill-down views
to static Python output. Keep both, for the reasons above.

---

## FILE LAYOUT

```
gimi-gimi-pipeline/
├── README.md                  ← plain-English overview, start here
├── HOW-IT-WORKS.md            ← the explain-it-simply doc
├── TROUBLESHOOTING.md         ← what to do when it breaks
├── .env.example               ← NAMES of required secrets, values left blank
├── .gitignore                 ← must include .env and data/ 
├── requirements.txt
├── config.py                  ← non-secret constants (spreadsheet ID,
│                                account IDs, campaign names, window length)
├── fetch_shopify.py           ← gets raw Shopify numbers
├── fetch_meta.py              ← gets raw Meta Ads numbers
├── fetch_gads.py              ← gets raw Google Ads numbers
├── compute_metrics.py         ← calculates the headline numbers
├── write_sheets.py            ← writes computed headlines + raw tabs
├── run_pipeline.py            ← runs everything in order, alerts on failure
├── data/                      ← saved sample data for development (gitignored)
└── .github/workflows/
    └── daily-refresh.yml      ← the daily timer
```

---

## BUILD ORDER (follow this sequence — it matters)

1. Build and run the three fetchers first. **Save their output to `data/` as
   CSV or JSON.** This becomes the sample data used to develop everything
   downstream. Do not build compute or write against live APIs; that is slow,
   burns rate limits, and makes iteration painful.
2. Build `compute_metrics.py` against those saved files, running it repeatedly
   until the numbers are right.
3. Build `write_sheets.py` against a **copy** of the spreadsheet, not the live
   one, until it is reliably producing the correct layout.
4. Only then point it at the live sheet and wire up the scheduler.

`data/` must be in `.gitignore`. It contains real business numbers and should
not be committed.

---

## SECRETS HANDLING — NON-NEGOTIABLE

Live credentials (Shopify admin token, Meta access token, Google Ads developer
and refresh tokens, Google Sheets service account key) let whoever holds them
spend money on ad accounts and read customer data.

- **Never** write a real credential into any file in the repository. Not in a
  config file, not in a comment, not in an example, not in a file labelled
  private. Private repos still get cloned, shared, and occasionally flipped
  public.
- Load every credential from an environment variable.
- Commit a `.env.example` listing only the variable NAMES with blank values,
  as a checklist of what needs setting up.
- Add `.env` to `.gitignore` so a local copy holding real values can never be
  committed by accident.
- In production the values live in **GitHub Actions Secrets** (repo Settings →
  Secrets and variables → Actions). Explain in the README, step by step and
  naming the exact menus and buttons, how the owner adds and rotates these.
- The README must state plainly: if a token is ever pasted into a chat, a doc,
  a Slack message, or committed by mistake, regenerate it on the platform
  immediately. Include how to regenerate each one.

---

## PHASE 1 — FETCHERS

Each fetcher is a standalone script calling the platform's API directly. No
MCP, no agent loop, no AI.

First investigate whether the existing Composio-connected accounts (Shopify,
Meta via GoMarble, Google Ads via GoMarble, Sheets) can be called directly
through Composio's own Python SDK or REST endpoint. That reuses existing OAuth
and avoids redoing app review and developer-token setup from scratch. If it is
not practical for a given source, fall back to the official SDK
(`shopify` / `facebook-business` / `google-ads`).

**Report which path you used for each source and why.** Real setup cost, real
trade-offs. Do not pick silently.

**fetch_shopify.py** — two queries per `rebuild-prompt` §1A, 35-day rolling
window, merged by date into `date, sessions, atc, checkouts, orders, revenue`.

**fetch_meta.py** — same fields, same `action_type` mapping, same pagination
requirement as §1B. Handle the large-response-written-to-file case explicitly;
do not assume the response always comes back inline.

**fetch_gads.py** — same GAQL query as §1C. GAQL has no GROUP BY or JOIN; do
not try to aggregate inside the query.

Every fetcher must:
- Save its output to `data/` so it can be reused for development.
- Fail loudly (raise an error) if the API errors or returns nothing. Never
  write an empty file and let later steps assume all is well.
- Record how many rows it fetched, for the conductor's sanity check.

---

## PHASE 2 — COMPUTE (headline numbers only)

`compute_metrics.py` reads the three raw tables and produces, using pandas:

1. **Shopify daily overview** — sessions, ATC, checkouts, orders, revenue,
   spend (four named Meta campaigns plus all Google Ads, per §2C), ROAS, AOV,
   A2C %, checkout %, checkout-to-order %.
2. **Meta summary row** — the TOTAL row from §2D with all derived metrics
   (frequency, CPM, CTR, CPC, ROAS, thruplay %, hook rate).
3. **Google Ads summary row** — the TOTAL row from §2E, with reach, frequency,
   LPV, ATC and checkout explicitly marked `N/A`, not blank and not 0. That
   distinction is deliberate in the original doc.

The day-on-day drill-down views are NOT computed here. They stay
formula-driven off the RAW_ tabs (see the architecture decision above).

**Fix these flaws from the original design while you are here:**

- The spend rollup uses four hardcoded Meta campaign names. Also compute
  **total Meta spend across ALL campaigns** and diff it against the
  four-campaign sum. If the difference is non-zero, flag it in the run
  summary and write the flag into a visible cell on the dashboard. In the old
  design a renamed or newly added campaign silently vanished from spend,
  quietly inflating ROAS with no error anywhere.
- Sanity checks before handing to the writer: spend not negative, revenue not
  wildly out of line with the trailing 7-day average, row counts from each
  source non-zero, dates continuous with no unexplained gaps. If a check
  fails, do NOT write. Raise, and let the conductor alert.
- Write a "last successful refresh" timestamp (IST) into a visible cell on the
  dashboard, updated only after everything has succeeded. If the pipeline
  stops running, a stale timestamp makes it obvious at a glance.

---

## PHASE 3 — WRITE

`write_sheets.py` writes two things into the existing spreadsheet (same
`spreadsheetId`, same tab names).

**3A. Raw tabs (feeds the existing formulas).** Write clean rows into
`RAW_Shopify`, `RAW_Meta`, `RAW_GAds` exactly as specified in §2A, same column
order. The existing `Lists` tab, dropdowns, data validation, and all the
drill-down formulas on the Shopify / Meta Ads / Google Ads tabs keep working
untouched.

**Important:** the existing formulas have hardcoded row ceilings
(`$A$400`, `$A$5000`, `$A$199`). Since the 35-day rolling window caps row
count, this is currently safe, but check the actual row counts against those
ceilings on every run and raise a warning if within 20% of the limit. Document
in HOW-IT-WORKS.md that extending the date window requires updating those
formula ranges.

**3B. Computed headline cells.** Write the Python-computed overview and summary
values as static numbers into their cells, replacing the formulas that
currently calculate them. These cells must not contain formulas after this
build.

**Writes must be effectively atomic.** Build everything in memory first. Only
clear and overwrite once all three sources have fetched, computed and passed
sanity checks. Never clear a tab before its replacement is ready. In the old
design a mid-write failure left a half-populated tab feeding the dashboard,
with no warning.

Respect the 60 reads/min and 60 writes/min rate limit; chunk writes.

---

## PHASE 4 — CONDUCTOR AND SCHEDULING

`run_pipeline.py`:
1. Runs fetch → compute → write in order.
2. Catches failures at each step and logs which step failed and why, **in
   plain language**, for example: "Could not get data from Meta Ads. The
   access token may have expired. See TROUBLESHOOTING.md section 3." Keep the
   technical detail underneath, but lead with the human explanation.
3. Sends a run summary to a webhook (Slack or email, whichever is simpler) on
   **both success and failure**. Include rows written per source, the spend
   reconciliation result, and any warnings. This is not optional. The old
   Cowork setup at least told the user what it did each day; a silent script
   would be a downgrade. Include a one-line headline in the message (spend,
   revenue, ROAS for yesterday) so the message is worth reading.
4. Exits with a non-zero code on failure so the scheduler marks the run failed.

**Scheduling — default: GitHub Actions.** Free, no separate cloud account,
secrets in the repo's encrypted Actions secrets, cron for daily at 10:45 AM
IST. GitHub cron runs in UTC, so convert and comment the conversion clearly in
the workflow file. If there is a strong reason to prefer Google Cloud Scheduler
plus a Cloud Function, say so. Reversible choice.

Write `.github/workflows/daily-refresh.yml`: cron trigger, checkout repo,
install `requirements.txt`, run `run_pipeline.py`, secrets injected as
environment variables. Also enable `workflow_dispatch` so the owner can click
"run now" to test.

---

## PHASE 5 — PARALLEL RUN VALIDATION (do not skip)

Before switching the Cowork scheduled task off, run both systems side by side
for at least three consecutive days.

- Each day, compare the Python-produced numbers against the Cowork-produced
  numbers for the same date range, cell by cell on the headline metrics.
- Meta total spend must match to the rupee. Revenue, orders, sessions must
  match exactly. Derived ratios must match to two decimal places.
- Any discrepancy is a bug in the new pipeline until proven otherwise. Do not
  assume the new numbers are right because the code is newer.
- Document the comparison results. Only after three clean days should the
  Cowork task be disabled.

State clearly in the handover: the goal is numbers **identical** to today's,
delivered more reliably. Different numbers mean something is wrong.

---

## PHASE 6 — DOCUMENTATION (mandatory)

Three documents, written for someone who has never written a line of code and
will be alone with this when it breaks.

### 6A. `README.md` — the front door, kept short

- What this does, in three sentences, in business terms: pulls the last 35
  days of ad and sales numbers from three places, does the math, updates one
  Google Sheet, every morning.
- Where the live dashboard is (link).
- When it runs and what to expect (a message every day saying it worked or it
  did not).
- One-time setup: getting each credential, and exactly where to paste it into
  GitHub Actions Secrets. Screenshot-level detail in words: which menu, which
  button, what the field is called.
- How to run it manually to test, before trusting the schedule.
- A pointer to TROUBLESHOOTING.md if something looks wrong.

### 6B. `HOW-IT-WORKS.md` — the explain-it-simply doc

This is what lets a non-technical owner reason about the system well enough to
fix it with Claude's help. Must cover:

- **Business context first.** What the funnel is (someone sees an ad, clicks,
  lands on the site, adds to cart, starts checkout, buys), and what each metric
  means in plain terms and why anyone cares. ROAS, CPM, CTR, AOV, spend, each
  defined in one line without assuming marketing knowledge.
- **The pipeline as a simple story.** For example: "Every morning at 10:45 a
  timer wakes up. It sends three messengers out, one to Shopify, one to Meta,
  one to Google Ads. Each brings back a table of numbers. A fourth script does
  the arithmetic on the important totals. A fifth types everything into the
  Google Sheet. If any messenger fails to come back, nothing gets written and
  you get a message." Include a simple diagram (ASCII or Mermaid).
- **Why some cells are calculated by Python and some by the sheet.** Explain
  the hybrid plainly: the headline numbers are calculated and double-checked
  before being written, because those get acted on; the dropdown drill-down
  views still calculate inside the sheet, which is why the dropdowns still
  work. The owner needs to understand this or they will be confused when they
  click a cell and sometimes see a formula and sometimes a number.
- **What each file does**, one short paragraph each, in the order they run.
  What goes IN and what comes OUT. No function-level detail.
- **Where each number in the sheet comes from.** For every column in the
  dashboard, name the source and the script (or the sheet formula) that
  produced it. This is the most useful table in the doc: when a number looks
  wrong, the owner needs to know which file to open.
- **What is fragile and why.** Access tokens expire. Platforms rename fields.
  Campaign names are hardcoded in `config.py` and must be updated when
  campaigns change. Sheet formulas have hardcoded row limits that break if the
  date window is extended. Name each fragility and where it lives.
- **What to change for common requests.** "I want a new metric added" → which
  file. "We launched a new campaign" → which file, which line. "I want it to
  run at a different time" → which file, which line. "I want a longer date
  range" → which file, plus the warning about sheet formula row limits.

### 6C. `TROUBLESHOOTING.md` — the break-glass doc

Symptom → likely cause → what to do. Every failure the pipeline can produce
must appear here, matched to the exact wording of the error message the
pipeline prints, so the owner can search for it.

Cover at minimum:
- The sheet did not update today at all (check the timestamp cell first).
- The sheet updated but a whole column is empty or zero.
- Spend looks too low or ROAS looks impossibly high (point at the campaign
  reconciliation flag).
- One source is missing but the others worked.
- Token expired or authentication failed, for each of the four credentials,
  with regeneration steps for each.
- The dropdowns stopped filtering correctly.
- The daily alert message stopped arriving.

For each entry, end with a copy-paste-ready line the owner can hand to Claude,
along the lines of: "Paste this into Claude: 'My Gimi Gimi pipeline failed with
this error [paste error]. The relevant file is [X]. Here is that file [paste
file]. What is wrong and how do I fix it?'" Teaching the owner how to get help
is part of the deliverable.

---

## THINGS TO CONFIRM RATHER THAN ASSUME

- Composio-direct vs. official SDK per source. Report the choice and reasoning
  for each of Shopify, Meta, Google Ads and Sheets.
- Where the alert goes (Slack webhook vs. email) and who receives it.
- Who will have access to the GitHub repo before secrets are loaded into it.
  Anyone with repo settings access effectively holds the keys to live ad spend
  and store data. This is a one-way door.