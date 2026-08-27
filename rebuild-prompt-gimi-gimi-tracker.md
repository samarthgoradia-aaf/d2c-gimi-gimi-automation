# MASTER REBUILD PROMPT — Gimi Gimi Daily Performance Tracker

> Use this prompt verbatim if the tracker sheet or its scheduled refresh is ever lost, deleted, or needs to be rebuilt from scratch. It contains every step, formula, and pitfall from the original build. Written to be executed by Claude Sonnet 5 in Cowork mode.

---

## ROLE

You are a Data Engineer building an automated Google Sheets reporting dashboard that integrates Shopify, Meta Ads, and Google Ads data, refreshed daily at 11:00 AM IST. Follow this document exactly — every query, formula, cell address, and column order is deliberate. Do not improvise structure. Use a task list (TaskCreate/TaskUpdate) to track the phases below.

## CONNECTORS & ACCOUNTS (verify all four BEFORE building anything)

1. **Shopify** — native Shopify connector. Store: **Gimi Gimi Foods** (gimigimifoods.com, INR, IST). Verify with `get-shop-info`. Data via `run-analytics-query` (ShopifyQL).
2. **Meta Ads** — GoMarble MCP. Account: **"New GG Ads"**, `act_868396352281563`. Verify with `facebook_list_ad_accounts`. Data via `facebook_get_adaccount_insights`.
3. **Google Ads** — GoMarble MCP. Customer ID: **4250828752** (AlimentoAgroFoods Pvt Ltd, direct access — do NOT pass manager_id). Verify with `google_ads_list_accounts`. Data via `google_ads_run_gaql`.
4. **Google Sheets** — Composio connector, account **aiparth011@gmail.com**. Verify via `COMPOSIO_SEARCH_TOOLS` (toolkit `googlesheets`, connection must be ACTIVE). Rate limits: max 60 reads/min and 60 writes/min.

If any connector is missing, STOP and report to the user before building. Do not overcommit.

---

## PHASE 1 — FETCH RAW DATA (last 30–35 days through today)

### 1A. Shopify (two ShopifyQL queries, merge by date)
```
FROM sessions SHOW sessions, sessions_with_cart_additions, sessions_that_reached_checkout TIMESERIES day SINCE -35d UNTIL today
FROM sales SHOW orders, total_sales TIMESERIES day SINCE -35d UNTIL today
```
Merge into rows: `date, sessions, atc, checkouts, orders, revenue`. Dates as `YYYY-MM-DD` strings. Note: `sessions_that_reached_checkout` = the "Checkouts" metric. Revenue = `total_sales` (can be negative on refund days — keep as-is).

### 1B. Meta Ads (ad-level, daily grain)
Call `facebook_get_adaccount_insights` with:
- `act_id`: `act_868396352281563`
- `level`: `ad`
- `time_increment`: `1`
- `time_range`: `{"since":"<start>","until":"<today>"}` (35-day window)
- `filtering`: `[{"field":"campaign.name","operator":"CONTAIN","value":"GG_"},{"field":"impressions","operator":"GREATER_THAN","value":0}]`
- `fields`: `["campaign_name","adset_name","ad_name","spend","impressions","reach","frequency","inline_link_clicks","actions","action_values","video_thruplay_watched_actions","video_p25_watched_actions","video_p50_watched_actions","video_p75_watched_actions","video_p100_watched_actions"]`
- `limit`: 500

**Pitfalls (critical):**
- Follow ALL pagination via `facebook_fetch_pagination_url` until no `paging.next`, and check `_gomarble_meta_insights_data_quality.paging_next_present` is false.
- The response is huge (~2MB) and will be dumped to a file instead of returned inline. Parse it with Python via the bash sandbox — the file path given in the error/notice is accessible under the session mount (look under `.claude/projects/.../tool-results/`). Do NOT try to read it with the Read tool (lines too long); use `json.load` in Python.
- Extract per row, exact column order:
  `date_start, campaign_name, adset_name, ad_name, spend, impressions, reach, frequency, inline_link_clicks, LPV, ATC, Checkout, Purchases, Revenue, Video3s, Thruplay, P25, P50, P75, P100`
  where from the `actions` array (match `action_type`): LPV=`landing_page_view`, ATC=`omni_add_to_cart` (fallback `add_to_cart`), Checkout=`omni_initiated_checkout` (fallback `initiate_checkout`), Purchases=`omni_purchase` (fallback `purchase`), Video3s=`video_view`; Revenue=`omni_purchase` from `action_values`; Thruplay/P25/P50/P75/P100 = the `video_view` value inside `video_thruplay_watched_actions` / `video_p25_watched_actions` / etc. Missing action types = 0.
- Sort rows by date, campaign, adset, ad. Round floats to 2 dp. Expect roughly 900–1,200 rows for 30 days.
- Reach and frequency are non-additive — store them raw per ad-day; the dashboard derives aggregate frequency as impressions/reach and labels summed reach as approximate.

### 1C. Google Ads (campaign-level, daily grain)
```
SELECT segments.date, campaign.name, metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions, metrics.conversions_value
FROM campaign
WHERE segments.date DURING LAST_30_DAYS AND metrics.impressions > 0
ORDER BY segments.date
```
GAQL is NOT SQL — no GROUP BY/JOIN/aggregates. The response includes a `cost` field already in currency units (else use cost_micros/1e6). Rows: `date, campaign, spend, impressions, clicks, conversions, conv_value`. It's normal if the account has few campaigns (historically only `GG_Sales_PMax`) or gaps/no recent spend.

---

## PHASE 2 — BUILD THE SPREADSHEET

Create spreadsheet titled **"Gimi Gimi Daily Performance Tracker"** (`GOOGLESHEETS_CREATE_GOOGLE_SHEET1`). Record the `spreadsheetId`. Then create tabs (`GOOGLESHEETS_ADD_SHEET`, no `index` param when parallel):
- Rename default Sheet1 (sheetId 0) → **Shopify** (via `GOOGLESHEETS_UPDATE_SHEET_PROPERTIES`, fields="title")
- **Meta Ads** (200 rows × 26 cols)
- **Google Ads** (200 rows × 20 cols)
- **RAW_Shopify** (500 × 10), **RAW_Meta** (5000 × 22), **RAW_GAds** (1000 × 10), **Lists** (300 × 12)

Record each tab's numeric sheetId (needed for data validation).

### 2A. Write raw data (all writes: `value_input_option: USER_ENTERED`)
- `RAW_Shopify!A1`: header `date, sessions, atc, checkouts, orders, revenue` + daily rows.
- `RAW_GAds!A1`: header `date, campaign, spend, impressions, clicks, conversions, conv_value` + rows.
- `RAW_Meta!A1`: header `date, campaign, adset, ad, spend, impressions, reach, frequency, link_clicks, lpv, atc, checkout, purchases, revenue, video_3s, thruplay, p25, p50, p75, p100` + all rows. **Write in chunks of ~200 rows** per `GOOGLESHEETS_VALUES_UPDATE` call (payload size limits). Keep total rows < 5000 (formulas reference row 5000).

### 2B. Lists tab (drives cascading dropdowns)
```
A1: (All)    B1: (All)    C1: (All)    D1: (All)
A2: =SORT(UNIQUE(FILTER(RAW_Meta!B2:B5000,RAW_Meta!B2:B5000<>"")))
B2: =IFERROR(SORT(UNIQUE(FILTER(RAW_Meta!C2:C5000,(RAW_Meta!C2:C5000<>"")*IF('Meta Ads'!$B$4="(All)",1,RAW_Meta!B2:B5000='Meta Ads'!$B$4)))),"")
C2: =IFERROR(SORT(UNIQUE(FILTER(RAW_Meta!D2:D5000,(RAW_Meta!D2:D5000<>"")*IF('Meta Ads'!$B$4="(All)",1,RAW_Meta!B2:B5000='Meta Ads'!$B$4)*IF('Meta Ads'!$B$5="(All)",1,RAW_Meta!C2:C5000='Meta Ads'!$B$5)))),"")
D2: =SORT(UNIQUE(FILTER(RAW_GAds!B2:B1000,RAW_GAds!B2:B1000<>"")))
```
This makes Ad Set options cascade from the selected Campaign, and Ad options cascade from both.

### 2C. TAB 1 — Shopify (Daily Overview)
- `A1`: title "GIMI GIMI — DAILY OVERVIEW (Shopify + Meta Tier2/FocusCities + Google Ads)"
- `A2`:"Start Date", `B2`: default start date (e.g. 30 days ago). `A3`:"End Date", `B3`: today. (Entered as YYYY-MM-DD, USER_ENTERED parses to dates.)
- `A5:L5` headers: `Date, Sessions, Add to Carts, Checkouts, Orders, Revenue, Spends, ROAS, AOV, A2C %, Checkout %, Checkout to Order %`
- `A6` = "TOTAL". `B6:F6` = SUMIFS over RAW_Shopify cols B–F with `RAW_Shopify!$A$2:$A$400,">="&$B$2` and `"<="&$B$3`.
- `G6` (Spends) — **ONLY these four Meta campaigns + all Google Ads**:
```
=SUMIFS(RAW_Meta!$E$2:$E$5000,RAW_Meta!$A$2:$A$5000,">="&$B$2,RAW_Meta!$A$2:$A$5000,"<="&$B$3,RAW_Meta!$B$2:$B$5000,"GG_Sales_Catalog_Tier2")
+SUMIFS(...,"GG_Sales_Media_Tier2")+SUMIFS(...,"GG_Sales_Media_FocusCities")+SUMIFS(...,"GG_Sales_Catalog_FocusCities")
+SUMIFS(RAW_GAds!$C$2:$C$1000,RAW_GAds!$A$2:$A$1000,">="&$B$2,RAW_GAds!$A$2:$A$1000,"<="&$B$3)
```
(each `SUMIFS(...)` repeats the same date conditions; exact campaign names, case-sensitive match not required by SUMIFS but use them verbatim)
- `H6`=IFERROR(F6/G6,"") ROAS · `I6`=IFERROR(F6/E6,"") AOV · `J6`=IFERROR(C6/B6,"") · `K6`=IFERROR(D6/C6,"") · `L6`=IFERROR(E6/D6,"")
- `A7` (spilling date column):
  `=IFERROR(SORT(FILTER(RAW_Shopify!$A$2:$A$400,(RAW_Shopify!$A$2:$A$400>=$B$2)*(RAW_Shopify!$A$2:$A$400<=$B$3))),"")`
- `B7:F7` — one MAP formula per column (spills the whole column):
  `=MAP($A$7:$A$400,LAMBDA(d,IF(d="","",SUMIFS(RAW_Shopify!$B$2:$B$400,RAW_Shopify!$A$2:$A$400,d))))` (change the sum column per metric)
- `G7` — same MAP pattern wrapping the 4-campaign + GAds spend expression with date `d`.
- `H7:L7` — ratio columns via ARRAYFORMULA, e.g. `H7`:
  `=ARRAYFORMULA(IF($A7:$A400="","",IFERROR($F7:$F400/$G7:$G400,"")))` (I=F/E, J=C/B, K=D/C, L=E/D)

### 2D. TAB 2 — Meta Ads
- `A1` title. Controls: `A2`:"Start Date"/`B2`, `A3`:"End Date"/`B3`, `A4`:"Campaign"/`B4`="(All)", `A5`:"Ad Set"/`B5`="(All)", `A6`:"Ad"/`B6`="(All)".
- `A8`: "VIEW 2.1 — SUMMARY / TOTAL FOR SELECTION"
- `A9:W9` headers: `Date, Spends, Impressions, Reach, Frequency, CPM, Link Clicks, CTR (Link), CPC, LPV, Add to Carts, Checkouts Initiated, Purchases, Revenue, ROAS, Video Views (3s), Thruplays, Thruplay %, Hook Rate, Video 25%, Video 50%, Video 75%, Video 100%`
- `A10`="TOTAL". Additive columns (B,C,D,G,J,K,L,M,N,P,Q,T,U,V,W) each use this SUMIFS template (change only the sum column — RAW_Meta col E=spend, F=impr, G=reach, I=clicks, J=lpv, K=atc, L=checkout, M=purch, N=rev, O=video3s, P=thruplay, Q=p25, R=p50, S=p75, T=p100):
```
=SUMIFS(RAW_Meta!$E$2:$E$5000,
  RAW_Meta!$A$2:$A$5000,">="&$B$2, RAW_Meta!$A$2:$A$5000,"<="&$B$3,
  RAW_Meta!$B$2:$B$5000,IF($B$4="(All)","<>",$B$4),
  RAW_Meta!$C$2:$C$5000,IF($B$5="(All)","<>",$B$5),
  RAW_Meta!$D$2:$D$5000,IF($B$6="(All)","<>",$B$6))
```
  Derived: `E10`=C10/D10 (Frequency) · `F10`=B10/C10*1000 (CPM) · `H10`=G10/C10 (CTR) · `I10`=B10/G10 (CPC) · `O10`=N10/B10 (ROAS) · `R10`=Q10/P10 (Thruplay %) · `S10`=P10/C10 (Hook Rate) — all wrapped in IFERROR(...,"").
- `A12`: "VIEW 2.2 — DAY-ON-DAY BREAKDOWN". `A13:W13` = same headers.
- `A14` spilling dates:
```
=IFERROR(SORT(UNIQUE(FILTER(RAW_Meta!$A$2:$A$5000,(RAW_Meta!$A$2:$A$5000>=$B$2)*(RAW_Meta!$A$2:$A$5000<=$B$3)*IF($B$4="(All)",1,RAW_Meta!$B$2:$B$5000=$B$4)*IF($B$5="(All)",1,RAW_Meta!$C$2:$C$5000=$B$5)*IF($B$6="(All)",1,RAW_Meta!$D$2:$D$5000=$B$6)))),"")
```
- Additive day-on-day columns = MAP over `$A$14:$A$199` with the same SUMIFS template using date `d` instead of the date-range pair. Ratio columns = ARRAYFORMULA over `$A14:$A199` (same ratios as summary row).

### 2E. TAB 3 — Google Ads
- Controls: `B2` start, `B3` end, `A4`:"Campaign"/`B4`="(All)".
- `A6`:"SUMMARY / TOTAL FOR SELECTION"; `A7:O7` headers: `Date, Spends, Impressions, Reach, Frequency, CPM, Link Clicks, CTR (Link), CPC, LPV, Add to Carts, Checkouts Initiated, Purchases, Revenue, ROAS`.
- `A8`="TOTAL": SUMIFS on RAW_GAds (C=spend, D=impr, E=clicks, F=conversions→Purchases, G=conv_value→Revenue) with date range + `RAW_GAds!$B$2:$B$1000,IF($B$4="(All)","<>",$B$4)`. Derived: CPM=B/C*1000, CTR=G/C, CPC=B/G, ROAS=N/B (IFERROR-wrapped). Columns D, E, J, K, L = literal text `N/A` (Google Ads has no daily Reach/Frequency/LPV/ATC/Checkout at campaign level).
- `A10`:"DAY-ON-DAY BREAKDOWN"; `A11:O11` headers; `A12` = FILTER/SORT/UNIQUE spill of RAW_GAds dates in range with campaign filter; MAP formulas over `$A$12:$A$199` for additive cols; ARRAYFORMULA for ratios; `=ARRAYFORMULA(IF($A12:$A199="","","N/A"))` for the N/A cols.

### 2F. Data validation (dropdowns) — `GOOGLESHEETS_SET_DATA_VALIDATION_RULE`
All with mode=SET, `validation_type: ONE_OF_RANGE`, `strict: false` (so "(All)" survives list changes), `show_custom_ui: true`. Indices are 0-based, end-exclusive:
- Meta Ads sheetId, row 3→4, col 1→2 → source `Lists!A1:A50` (Campaign)
- Meta Ads, row 4→5, col 1→2 → `Lists!B1:B100` (Ad Set)
- Meta Ads, row 5→6, col 1→2 → `Lists!C1:C200` (Ad)
- Google Ads sheetId, row 3→4, col 1→2 → `Lists!D1:D50` (Campaign)

### 2G. Formatting — `GOOGLESHEETS_FORMAT_CELL` (clean, high-contrast; no decoration)
IMPORTANT: this tool defaults to a gray background if you omit color — always pass `background_color` explicitly (`#ffffff` for data, `#f1f3f4` for header rows, `#fff8e1` for the editable control cells B2:B3/B4/B5/B6).
- Headers + TOTAL rows + control labels: bold, `#f1f3f4` (headers) / white (labels).
- Numbers: pattern `#,##0.00` on — Shopify `B6:I400`; Meta `B10:W199`; GAds `B8:O199`.
- Percentages: pattern `0.00%` on — Shopify `J6:L400`; Meta `H10:H199` and `R10:S199`; GAds `H8:H199`.
- Dates: pattern `yyyy-mm-dd` on date spill columns (Shopify `A7:A400`, Meta `A14:A199`, GAds `A12:A199`) and all Start/End input cells.

### 2H. Verify before finishing
`GOOGLESHEETS_BATCH_GET` on `Shopify!A5:L9`, `'Meta Ads'!A9:S16`, `'Google Ads'!A7:O14`, `Lists!A1:D8`. Confirm: totals non-empty, Meta TOTAL Spends equals the Python-computed sum of the raw spend column (cross-check to the rupee), cascading lists populated, no #REF/#N/A. Fix before reporting done.

---

## PHASE 3 — DAILY AUTOMATION (11:00 AM IST)

Create a scheduled task (`create_scheduled_task`): id `gimi-gimi-daily-refresh`, cron `45 10 * * *` local time (finishes before 11:00). The task prompt must be fully self-contained (each run has no memory) and instruct: re-run Phase 1 for a rolling 35-day window (overwrite full window to capture late-attributed conversions), clear then rewrite ONLY the three RAW_ tabs (`GOOGLESHEETS_SPREADSHEETS_VALUES_BATCH_CLEAR` then chunked `GOOGLESHEETS_VALUES_UPDATE`), never touch the dashboard/Lists tabs (formulas recalc automatically), verify `Shopify!A5:L7` non-empty, and report rows written per tab + any failed source (partial refresh is better than none). Include the spreadsheet ID and all account IDs verbatim in that prompt. Tell the user: runs execute while the Claude app is open (missed runs fire on next launch), and they should click "Run now" once to pre-approve tool permissions.

---

## KNOWN LIMITATIONS (state these honestly to the user)
- Dropdowns are single-select with "(All)" — Sheets API has no true multi-select slicers.
- No Apps Script can be embedded via API; scheduling runs from Cowork's native scheduler.
- Meta daily Reach summed across ads is slightly overstated (non-additive metric).
- Google Ads: Reach/Frequency/LPV/ATC/Checkouts are N/A at daily campaign level.
- Composio Sheets rate limit 60 writes/min — chunk and batch writes.
