# FRED MCP Server Guide for an Autonomous Scoring Agent

## Purpose of this server

This MCP server gives the agent controlled access to the **Federal Reserve Economic Data (FRED)** catalog and time series API.

Its job in this project is to provide **macro context**, not local Waterloo operational data.

Use this server to enrich the model with broad signals such as:

- interest rates
- inflation
- shelter inflation
- labour market backdrop
- construction and housing finance context
- national or provincial trend checks

Do **not** treat FRED as the main source for Waterloo-region sector scores. It is best used as a **secondary context layer** alongside Waterloo-specific sources such as municipal open data, Statistics Canada, or sector-specific local feeds.

## When this server is useful

Use this server when the agent needs:

- a time series for macroeconomic context
- a quick way to discover whether a public economic indicator exists
- historical observations with optional transformations
- a small number of trusted economic features to supplement sector scoring

Examples:

- housing score: add interest rate pressure, CPI, shelter inflation
- employment score: add broader labour market trend context
- affordability score: add inflation and cost-of-living pressure
- investment / growth score: add policy rate and macro cycle context

## When this server is not useful

Do not rely on this server for:

- Waterloo building permits
- Waterloo transit service levels
- local hospital wait times
- municipal water or wastewater capacity
- council approvals or local project milestones
- local GIS or parcel-level data

Those require local or sector-specific sources.

---

## Authentication and access

FRED requires an API key for API requests.

The MCP server should already be configured with a valid FRED API key before the agent uses it.

The agent should assume:

- the key is preconfigured
- tool calls should fail gracefully if the key is missing
- FRED access is intended for low-volume, targeted retrieval rather than broad crawling

---

## Tool surface

This MCP server exposes three tools:

1. `fred_search`
2. `fred_get_series`
3. `fred_browse`

### Recommended usage policy

For this project, the agent should primarily use:

- `fred_search`
- `fred_get_series`

Use `fred_browse` only as a fallback when search results are too noisy or when structured exploration by release or category is truly needed.

This keeps tool use small and focused.

---

## Core operating model

The agent should follow this sequence:

1. Use `fred_search` to find a likely series.
2. Inspect the result and choose the best series ID.
3. Use `fred_get_series` to retrieve observations.
4. Optionally use `fred_browse` only if search is insufficient.

The agent should avoid repeated exploratory browsing when a direct search is likely to work.

---

# Tool reference

## 1) `fred_search`

### Purpose

Search for candidate FRED series by keyword, tag, or simple filters.

This is the main discovery tool.

### Description

Finds economic data series based on text or series ID lookup. Use this tool before attempting to pull observations unless the exact series ID is already known.

### Parameters

#### `search_text` *(optional)*
Free-text query for matching titles and descriptions.

Best for:
- `"Canada CPI"`
- `"Canada unemployment"`
- `"policy rate"`
- `"shelter inflation"`
- `"housing starts Canada"`

#### `search_type` *(optional)*
Allowed values:
- `"full_text"`
- `"series_id"`

Use:
- `"full_text"` for normal discovery
- `"series_id"` only when checking a known series ID

#### `tag_names` *(optional)*
Comma-separated FRED tags to include.

Use sparingly. Over-filtering can reduce useful results.

#### `exclude_tag_names` *(optional)*
Comma-separated FRED tags to exclude.

Use sparingly.

#### `limit` *(optional)*
Maximum results to return.

Recommended:
- default search: `5` to `10`
- broader discovery: `15` to `25`

Keep this small to reduce agent overload.

#### `offset` *(optional)*
Pagination offset.

Use only when the first page is clearly insufficient.

#### `order_by` *(optional)*
Sort field.

Good defaults:
- `"popularity"`
- `"last_updated"`

#### `sort_order` *(optional)*
Allowed values:
- `"asc"`
- `"desc"`

Recommended:
- `"desc"` for `"popularity"` or `"last_updated"`

#### `filter_variable` *(optional)*
Allowed examples:
- `"frequency"`
- `"units"`
- `"seasonal_adjustment"`

Use only when necessary.

#### `filter_value` *(optional)*
Value tied to `filter_variable`.

Examples:
- monthly frequency
- percent units
- seasonally adjusted

### Best practices

Use `fred_search` when:
- the exact series ID is unknown
- multiple related indicators may exist
- the agent wants the most relevant economic series quickly

Avoid:
- huge limits
- repeated query variants with tiny wording changes
- combining many filters unless the search space is obviously too large

### Good example patterns

- Search for inflation series:
  - `search_text="Canada CPI"`
  - `limit=5`
  - `order_by="popularity"`
  - `sort_order="desc"`

- Search for shelter inflation:
  - `search_text="Canada shelter CPI"`
  - `limit=5`

- Search for labour context:
  - `search_text="Canada unemployment"`
  - `limit=5`

### Agent decision rule

Use this first unless the series ID is already known.

---

## 2) `fred_get_series`

### Purpose

Retrieve actual observation data for a known FRED series ID.

This is the main data retrieval tool.

### Description

Pulls a time series and supports date filtering, sorting, aggregation, and transformations.

### Parameters

#### `series_id` *(required)*
The FRED series identifier.

Examples:
- `"GDP"`
- `"UNRATE"`
- a Canada-related or other macro series returned from search

This must be a valid series chosen from `fred_search` results.

#### `observation_start` *(optional)*
Start date in `YYYY-MM-DD` format.

Use this to keep the time window relevant and reduce payload size.

#### `observation_end` *(optional)*
End date in `YYYY-MM-DD` format.

#### `limit` *(optional)*
Maximum observations.

Useful for:
- recent snapshots
- testing
- avoiding oversized outputs

#### `offset` *(optional)*
Pagination or skipping older entries.

Rarely needed for this project.

#### `sort_order` *(optional)*
Allowed values:
- `"asc"`
- `"desc"`

Recommended:
- `"asc"` for model ingestion
- `"desc"` for quick recent inspection

#### `units` *(optional)*
Transformation applied to the series.

Allowed values:
- `"lin"` = raw level
- `"chg"` = change from previous period
- `"ch1"` = change from year ago
- `"pch"` = percent change from previous period
- `"pc1"` = percent change from year ago
- `"pca"` = compounded annual rate of change
- `"cch"` = continuously compounded rate of change
- `"log"` = natural log

Recommended uses:
- `lin` for baseline features
- `pc1` for year-over-year trend features
- `pch` for month-over-month or period-over-period movement
- `chg` for absolute movement features

#### `frequency` *(optional)*
Aggregation frequency.

Allowed values:
- `"d"` daily
- `"w"` weekly
- `"m"` monthly
- `"q"` quarterly
- `"a"` annual

Use this when the raw data is too granular or when the model expects a consistent interval.

#### `aggregation_method` *(optional)*
Allowed values:
- `"avg"`
- `"sum"`
- `"eop"` (end of period)

Recommended:
- `avg` for averaged rates
- `sum` for additive flows
- `eop` for stock-like or end-period measures

### Best practices

Use `fred_get_series` when:
- the exact series ID is known
- the agent needs real observations for feature generation
- the agent wants transformed trend features from a macro series

Always try to:
- restrict the date range
- choose a transformation deliberately
- choose a frequency only when needed

Avoid:
- pulling full history unless necessary
- requesting many variant transformations for the same series in one pass
- using high-frequency data if the score updates monthly or quarterly

### Good example patterns

#### Raw series retrieval
- retrieve a series with:
  - `series_id=<known id>`
  - `observation_start="2018-01-01"`
  - `sort_order="asc"`
  - `units="lin"`

#### Year-over-year trend retrieval
- retrieve:
  - `series_id=<known id>`
  - `observation_start="2018-01-01"`
  - `units="pc1"`
  - `frequency="m"`

#### Quarterly macro summary
- retrieve:
  - `series_id=<known id>`
  - `observation_start="2015-01-01"`
  - `frequency="q"`
  - `aggregation_method="avg"`

### Agent decision rule

Use this after `fred_search` identifies the best candidate series.

---

## 3) `fred_browse`

### Purpose

Browse the FRED catalog through categories, releases, or sources.

### Description

This is a structured exploration tool. It is less important than search for this project.

### Parameters

#### `browse_type` *(required)*
Allowed values:
- `"categories"`
- `"releases"`
- `"sources"`
- `"category_series"`
- `"release_series"`

#### `category_id` *(optional)*
Category ID to inspect subcategories or series within a category.

Use only when browsing categories.

#### `release_id` *(optional)*
Release ID to inspect series within a release.

Use only when browsing releases.

#### `limit` *(optional)*
Maximum number of results.

Keep small:
- `5` to `15` is usually enough

#### `offset` *(optional)*
Pagination offset.

Use only if necessary.

#### `order_by` *(optional)*
Ordering field.

Use only when a specific sort is useful.

#### `sort_order` *(optional)*
Allowed values:
- `"asc"`
- `"desc"`

### Best practices

Use `fred_browse` only when:
- keyword search fails
- the agent knows the release or category structure matters
- a human has explicitly asked to explore the catalog structure

Avoid using this as the default discovery tool.

### Agent decision rule

Prefer `fred_search`. Only use `fred_browse` as fallback.

---

# Recommended tool policy for this project

## Minimal allowed tools

Preferred minimal configuration:

- `fred_search`
- `fred_get_series`

## Optional extra tool

Add only if needed:

- `fred_browse`

## Why this is the right size

This keeps the agent focused and prevents wasteful exploration while still allowing:

- discovery
- validation
- retrieval

---

# How this server supports the problem statement

## Role in the scoring pipeline

This MCP server should act as a **macro feature provider**.

It should not own the entire score-generation workflow.

Use it to create supporting features such as:

- inflation pressure indicators
- borrowing-cost pressure indicators
- broad employment conditions
- national or provincial demand backdrop
- construction or finance cycle context

## Suggested placement in the pipeline

1. Ingest Waterloo-local and sector-specific data first.
2. Use FRED to add macro context.
3. Normalize all features to a common date cadence.
4. Feed the merged features into the sector scoring model.

## Typical examples by sector

### Housing
Possible feature types:
- rate pressure
- inflation pressure
- shelter inflation trend
- macro housing cycle context

### Employment
Possible feature types:
- broad labour market trend
- macro slowdown or expansion context

### Affordability / Livability
Possible feature types:
- CPI trend
- shelter cost inflation
- real pressure proxies

### Investment / Growth
Possible feature types:
- financing conditions
- broad economic momentum

---

# Retrieval strategy for the agent

## Default strategy

### Step 1: Search
Use `fred_search` with a short and clear query.

Examples:
- `"Canada CPI"`
- `"Canada shelter CPI"`
- `"Canada unemployment"`
- `"Canada housing starts"`
- `"policy rate"`

### Step 2: Choose the best series
Prefer a series that is:
- clearly named
- regularly updated
- consistent with the feature definition
- not overly narrow or obscure

### Step 3: Pull observations
Use `fred_get_series` with:
- a reasonable date range
- appropriate transformation
- the lowest useful frequency

### Step 4: Convert into a model feature
Examples:
- latest value
- year-over-year change
- 3-month moving average after retrieval
- slope over trailing periods

---

# Parameter guidance for agents

## Search parameter defaults

Recommended defaults for `fred_search`:
- `search_type="full_text"`
- `limit=5`
- `order_by="popularity"`
- `sort_order="desc"`

Use filters only if the results are obviously noisy.

## Series retrieval defaults

Recommended defaults for `fred_get_series`:
- `sort_order="asc"`
- `units="lin"` unless a trend feature is needed
- specify `observation_start`
- omit `frequency` unless you need aggregation

## Browse parameter defaults

Recommended defaults for `fred_browse`:
- keep `limit` small
- use only the required browse ID
- avoid broad catalog walks

---

# Guardrails

## Use guardrails
The agent should:

- keep query counts low
- avoid repeated searches with tiny wording changes
- avoid broad browsing unless needed
- restrict date windows
- prefer stable macro indicators over obscure series
- log which series IDs are selected for reproducibility

## Do not
The agent should not:

- assume FRED contains Waterloo-local operational data
- use FRED as the primary housing, transit, healthcare, or infrastructure source for Waterloo
- ingest large numbers of loosely related series without a scoring rationale
- browse entire catalogs without a specific purpose

---

# Good and bad usage examples

## Good usage

### Good
Search for a broad inflation signal, choose one relevant series, and retrieve monthly year-over-year values for the last 8 years.

Why it is good:
- focused
- interpretable
- useful for scoring

### Good
Search for a broad labour backdrop and retrieve one monthly trend series.

Why it is good:
- low tool count
- high signal-to-noise

## Bad usage

### Bad
Run ten different searches for nearly identical phrases and keep twenty candidate series.

Why it is bad:
- wastes tokens
- creates ambiguity
- overloads the model

### Bad
Use FRED to answer Waterloo-specific operational questions.

Why it is bad:
- wrong data layer
- poor local fit

### Bad
Retrieve full history for many daily series without a feature plan.

Why it is bad:
- high payload
- low relevance

---

# Recommended agent prompt fragment

Use this as internal guidance for the agent:

> Use the FRED MCP server only for macroeconomic context. Prefer `fred_search` followed by `fred_get_series`. Use `fred_browse` only when search fails or when category/release exploration is necessary. Keep queries narrow, limits small, and date ranges relevant. Do not use FRED as the primary source for Waterloo-local sector metrics.

---

# Practical summary

## What this server is
A macroeconomic context server.

## What it is for
Adding a small number of high-value economic time series to sector scores.

## What tools matter most
- `fred_search`
- `fred_get_series`

## What tool is optional
- `fred_browse`

## Best use in this project
Use it as a secondary feature layer beside Waterloo-local data.

## Best configuration
Allow only:
- `fred_search`
- `fred_get_series`

Add `fred_browse` only if discovery needs it.