"""
Non-secret settings for the Gimi Gimi tracker pipeline.

Nothing in this file is a password or token — those come from environment
variables (see .env.example). This file is safe to read and safe to commit.
If a campaign name, account ID, or the run window ever needs to change, this
is the only file you touch.
"""
import os

# ─── The Google Sheet this pipeline writes into ─────────────────────────────
# Taken from the sheet URL:
# https://docs.google.com/spreadsheets/d/<THIS PART IS THE ID>/edit
#
# The default below is the LIVE tracker. To run against a test copy instead,
# set the SPREADSHEET_ID environment variable (in .env for local runs, or as a
# GitHub Actions secret) — it overrides this without a code change.
LIVE_SPREADSHEET_ID = "1-v-zWqlLKVHJlL7X2hIfaxmVDl21VtZI1gOhJDd40sg"
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "").strip() or LIVE_SPREADSHEET_ID

# ─── Shopify ───────────────────────────────────────────────────────────────
# The *.myshopify.com domain, NOT the public gimigimifoods.com address.
SHOPIFY_STORE_DOMAIN = "gimigimifoods.myshopify.com"
SHOPIFY_API_VERSION = "2025-01"

# ─── Meta (Facebook) Ads ───────────────────────────────────────────────────
# Ad account ID including the "act_" prefix.
META_AD_ACCOUNT_ID = "act_868396352281563"
META_API_VERSION = "v21.0"

# ─── Google Ads ────────────────────────────────────────────────────────────
# NOT used in v1. Kept here so v2 has it in one place.
GOOGLE_ADS_CUSTOMER_ID = "4250828752"

# ─── Run window ────────────────────────────────────────────────────────────
# Every run rebuilds the last N days in full, so late-attributed conversions
# get corrected. today - WINDOW_DAYS .. today  (about WINDOW_DAYS + 1 rows).
WINDOW_DAYS = 35

# Everything ("today", timestamps) is computed in this timezone.
TIMEZONE = "Asia/Kolkata"

# ─── Google Sheet tab names (must match the sheet exactly) ──────────────────
RAW_SHOPIFY_TAB = "RAW_Shopify"
RAW_META_TAB = "RAW_Meta"
RAW_GADS_TAB = "RAW_GAds"

# ─── Column order for each RAW tab (this is the header row) ─────────────────
# DO NOT reorder. The dashboard formulas reference these columns by position.
RAW_SHOPIFY_COLUMNS = [
    "date", "sessions", "atc", "checkouts", "orders", "revenue",
]
RAW_META_COLUMNS = [
    "date", "campaign", "adset", "ad", "spend", "impressions", "reach",
    "frequency", "link_clicks", "lpv", "atc", "checkout", "purchases",
    "revenue", "video_3s", "thruplay", "p25", "p50", "p75", "p100",
]
RAW_GADS_COLUMNS = [
    "date", "campaign", "spend", "impressions", "clicks", "conversions",
    "conv_value",
]

# ─── Row ceilings the existing sheet formulas assume ───────────────────────
# The dashboard formulas stop reading past these rows. The pipeline warns if
# a RAW tab gets within 20% of its ceiling. Raising the run window past ~35
# days means these (and the formulas in the sheet) must be raised too.
ROW_CEILINGS = {
    RAW_SHOPIFY_TAB: 400,
    RAW_META_TAB: 5000,
    RAW_GADS_TAB: 1000,
}

# ─── The four Meta campaigns that feed the "Spends" cell on the Shopify ─────
# overview tab. Used ONLY for the informational line in the daily email
# (the pipeline does not write headline cells in v1). If a core campaign is
# renamed or a new one is launched, update this list.
CORE_META_CAMPAIGNS = [
    "GG_Sales_Catalog_Tier2",
    "GG_Sales_Media_Tier2",
    "GG_Sales_Media_FocusCities",
    "GG_Sales_Catalog_FocusCities",
]
