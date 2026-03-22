# Urban Intelligence Platform
## City Planner AI Pipeline — Technical Specification
**Version 1.0 | March 2026 | Confidential — Internal Development Use**

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Agent Design](#3-agent-design)
4. [Scoring System](#4-scoring-system)
5. [Database Schema](#5-database-schema)
6. [API Reference](#6-api-reference)
7. [Frontend Architecture](#7-frontend-architecture)
8. [Environment Configuration](#8-environment-configuration)
9. [Development Roadmap](#9-development-roadmap)
10. [OpenAI Cost Estimates](#10-openai-cost-estimates)

---

## 1. Project Overview

The Urban Intelligence Platform (UIP) is a full-stack AI pipeline designed to assist city planners in evaluating municipal datasets against evidence-based benchmarks across five civic categories: **Housing, Transportation, Healthcare, Employment, and Placemaking**.

The system ingests data from heterogeneous sources — CSV uploads, REST/GraphQL API endpoints, and live data streams — and routes each through a multi-agent pipeline that classifies, fetches, summarises, embeds, and scores the data. All results are surfaced in an interactive React dashboard with an embedded AI agent the planner can query for policy intervention recommendations.

### 1.1 Goals

- Provide a unified ingestion layer that accepts structured data from any source format.
- Automate classification of data sources and fetch remote data when required.
- Generate LLM-produced summaries of each dataset and store semantic embeddings in pgvector.
- Score each dataset against hardcoded civic benchmarks, weighted by vector similarity and predefined category importance.
- Aggregate per-category scores (0–100) and present them on a planner dashboard.
- Expose a central AI agent capable of generating policy intervention recommendations on demand.

### 1.2 Non-Goals (v1.0)

- User authentication or multi-tenancy (single-planner deployment).
- Real-time streaming ingestion (polling cadence is acceptable for v1).
- Editable benchmarks via UI (hardcoded per category in v1; admin UI deferred).
- Multi-city comparative analytics.

### 1.3 Key Terminology

| Term | Definition |
|---|---|
| **Dataset** | A single ingested data object: one CSV upload, one API response, or one stream payload. |
| **Summary** | An LLM-generated structured prose description of a dataset's content and civic relevance. |
| **Embedding** | A 384-dimension float vector produced from a summary by OpenAI `text-embedding-3-small`. |
| **Category anchor** | A hardcoded reference embedding representing one of the five civic categories. |
| **Cosine similarity** | A float 0–1 representing how closely a dataset embedding matches a category anchor. |
| **Benchmark eval** | A float 0–1 produced by comparing dataset statistics against hardcoded category thresholds. |
| **Importance weight** | A predefined float per category (all five sum to 1.0) reflecting planning priority. |
| **Category score** | Final 0–100 score = `benchmark_eval × cosine_similarity × importance_weight × 100`, aggregated across all datasets for that category. |
| **Central agent** | A LangGraph ReAct agent with tool access to scores, summaries, and policy knowledge. |

---

## 2. System Architecture

### 2.1 High-Level Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18 + TypeScript, Tailwind CSS, Recharts, shadcn/ui |
| **Backend** | FastAPI (Python 3.11), Uvicorn, Pydantic v2 |
| **Agent framework** | LangGraph 0.2 (StateGraph nodes for each pipeline stage) |
| **LLM provider** | OpenAI GPT-4o (summarisation, agent reasoning) |
| **Embeddings** | OpenAI `text-embedding-3-small` (384 dimensions) |
| **Vector store** | PostgreSQL 15 + pgvector extension |
| **ORM / migrations** | SQLAlchemy 2.0 async + Alembic |
| **Task queue** | Celery + Redis (async ingestion jobs) |
| **Containerisation** | Docker Compose (Postgres, Redis, backend, frontend) |

### 2.2 Repository Structure

```
uip/
  backend/
    agents/
      classifier.py          # LangGraph node: detect type, fetch if endpoint
      summariser.py          # LangGraph node: GPT-4o structured summary
      central_agent.py       # ReAct agent: policy intervention QA
      graph.py               # StateGraph wiring all pipeline nodes
    scoring/
      benchmarks.py          # Hardcoded benchmark constants + eval functions
      scorer.py              # score = benchmark_eval x similarity x importance
      anchors.py             # Category anchor texts + precomputed embeddings
    db/
      models.py              # SQLAlchemy: Dataset, Embedding, Score tables
      embeddings.py          # pgvector insert, cosine query helpers
      session.py             # Async engine + session factory
    api/
      ingest.py              # POST /ingest (file or endpoint)
      scores.py              # GET /scores, GET /scores/{category}
      datasets.py            # GET /datasets, GET /datasets/{id}
      chat.py                # POST /agent/chat (central agent SSE stream)
    tasks/
      pipeline.py            # Celery task: run full agent graph on a dataset
    main.py                  # FastAPI app factory, router registration
    config.py                # Pydantic Settings (env vars)
  frontend/
    src/
      components/
        CategoryCard.tsx     # Score card per category
        ScoreChart.tsx       # Radar chart of all five categories
        DatasetTable.tsx     # Paginated list of ingested datasets
        AgentChat.tsx        # Streaming chat panel for central agent
        IngestForm.tsx       # Upload / endpoint input form
      pages/
        Dashboard.tsx        # Main planner view
        DatasetDetail.tsx    # Per-dataset summary + scores
      api/                   # Typed fetch wrappers
  docker-compose.yml
  alembic/                   # DB migrations
```

### 2.3 Data Flow — End to End

The complete pipeline for a single ingestion event:

1. Planner submits a CSV file or API endpoint URL via the React `IngestForm`.
2. `POST /ingest` validates the input and enqueues a Celery pipeline task, returning a `dataset_id` immediately.
3. The Celery task initialises the LangGraph `StateGraph` and invokes the **classifier node**.
4. The classifier determines input type. If it is an endpoint, it performs an HTTP GET and normalises the response to plain text. If CSV, it reads and formats the rows.
5. The **summariser node** sends normalised text to GPT-4o with a structured system prompt, producing a JSON summary object (`title`, `key_metrics`, `civic_relevance`, `data_quality_notes`).
6. The **embedding node** calls `text-embedding-3-small` on the summary text and stores both the summary and its 384-dim vector in pgvector.
7. The **scorer node** computes cosine similarity between the stored embedding and each of the five category anchor embeddings using the pgvector `<=>` operator.
8. For each category, the **benchmark evaluator** compares `key_metrics` from the summary against hardcoded thresholds, returning a `benchmark_eval` float 0–1.
9. Final category scores are written to the `category_scores` table: `score = benchmark_eval × cosine_similarity × importance_weight`, normalised to 0–100.
10. The dashboard polls `GET /scores` and re-renders category cards and the radar chart.

---

## 3. Agent Design

### 3.1 LangGraph Pipeline Graph

The ingestion pipeline is implemented as a LangGraph `StateGraph`. Each node is a pure function that receives the shared `PipelineState` TypedDict and returns a partial update. Nodes execute sequentially; no branching edges are needed in v1 beyond the classifier's fetch/skip decision.

```python
PipelineState = TypedDict({
    'dataset_id':   str,
    'raw_input':    str,           # file contents or endpoint URL
    'input_type':   str,           # 'csv' | 'endpoint' | 'stream'
    'fetched_text': str,           # normalised text after fetch
    'summary':      dict,          # GPT-4o structured summary
    'embedding':    list[float],   # 384-dim vector
    'similarities': dict[str, float],   # category -> cosine sim
    'scores':       dict[str, float],   # category -> 0-100 score
    'error':        str | None,
})
```

Graph wiring:

```python
graph = StateGraph(PipelineState)
graph.add_node("classifier",  classifier_node)
graph.add_node("summariser",  summariser_node)
graph.add_node("embedder",    embedding_node)
graph.add_node("scorer",      scorer_node)
graph.set_entry_point("classifier")
graph.add_edge("classifier", "summariser")
graph.add_edge("summariser", "embedder")
graph.add_edge("embedder",   "scorer")
graph.add_edge("scorer",     END)
pipeline = graph.compile()
```

---

### 3.2 Classifier Node

**Responsibility:** determine whether the input is a local CSV/file or a remote endpoint, fetch remote data if needed, and return normalised plain text.

> **Model:** `gpt-4o-mini` — lightweight one-shot classification. Full GPT-4o is not needed here; latency and cost matter at this stage.

#### 3.2.1 Classifier System Prompt

```
You are a data-type classifier for a city planning pipeline. Given an input
string, determine whether it is:
  (a) CSV or tabular text content
  (b) a URL pointing to a REST or GraphQL API endpoint
  (c) a raw JSON payload from a stream

Respond ONLY with a JSON object: {"type": "csv"|"endpoint"|"stream"}.
Do not include any preamble, explanation, or markdown fencing.
```

#### 3.2.2 Endpoint Fetch Logic

- If `type == "endpoint"`: issue HTTP GET with a 10s timeout.
- Response parsing: if JSON, flatten to key-value text lines; if CSV, pass as-is.
- All fetched content is truncated to **12,000 tokens** before passing to the summariser.
- If the endpoint returns 4xx/5xx, mark `state['error']` and skip downstream nodes.

---

### 3.3 Summariser Node

**Responsibility:** take normalised text and produce a structured JSON summary describing the dataset's content, key metrics, and civic relevance. This summary is the artifact that gets embedded and scored — its quality directly determines scoring accuracy.

> **Model:** `gpt-4o` at `temperature=0.2`. Quality of the summary directly determines the accuracy of cosine similarity scores downstream — a weak summary produces miscategorised embeddings. Temperature is set to 0.2 for consistency across re-runs.

#### 3.3.1 Summariser System Prompt

```
You are a civic data analyst embedded in a city planning AI system. You will
receive raw or semi-structured data from a municipal dataset. Your job is to
produce a structured JSON summary with exactly the following keys:

{
  "title": "<short descriptive title for this dataset>",
  "domain": "<one of: housing | transportation | healthcare | employment |
             placemaking | mixed | unknown>",
  "geography": "<city, region, or 'unknown'>",
  "time_period": "<year or date range, or 'unknown'>",
  "key_metrics": {
    "<metric_name>": <numeric_value_or_null>,
    ... (extract all quantitative metrics present in the data)
  },
  "civic_relevance": "<2-4 sentences on why this data matters to a city planner
                       and which planning categories it most directly informs>",
  "data_quality_notes": "<1-2 sentences on completeness, recency, known gaps,
                          or reliability caveats>"
}

Return ONLY the JSON object. No markdown fencing, no preamble, no explanation.
If a field cannot be determined, use null. Never hallucinate numeric metrics —
only extract values explicitly present in the input data.
```

#### 3.3.2 Summary Validation

- Response is parsed with `json.loads()`; a Pydantic `SummarySchema` validates all fields.
- If parsing fails, the node retries **once** with an appended correction instruction: `"Your previous response was not valid JSON. Return only the JSON object, nothing else."`
- If the second attempt fails, `state['error']` is marked and the dataset is stored without scoring.

---

### 3.4 Embedding Node

**Responsibility:** generate a 384-dimension embedding from the constructed summary text and store it alongside the summary in Postgres via pgvector.

> **Model:** `text-embedding-3-small` with `dimensions=384` — a smaller vector size that is sufficient for the category-matching task here while reducing storage footprint. The input to the embedding model is `civic_relevance` concatenated with formatted `key_metrics` — **not** the full raw data, which would degrade embedding quality by flooding the vector with non-semantic content.

#### 3.4.1 Embedding Input Construction

```python
def build_embed_input(summary: dict) -> str:
    metrics_str = ", ".join(
        f"{k}: {v}"
        for k, v in summary['key_metrics'].items()
        if v is not None
    )
    return (
        f"{summary['title']}. "
        f"{summary['civic_relevance']} "
        f"Key metrics: {metrics_str}."
    )
```

---

### 3.5 Scorer Node

**Responsibility:** compute the final 0–100 score for each of the five categories by combining benchmark evaluation, cosine similarity, and importance weight.

#### 3.5.1 Scoring Formula

```python
# Per dataset, per category:
score_i = benchmark_eval_i(summary) * cosine_sim_i * importance_weight_i * 100

# Aggregated across N datasets for category C:
category_score_C = weighted_mean(scores, weights=cosine_similarities)
```

#### 3.5.2 Cosine Similarity Query

```sql
-- pgvector <=> returns cosine distance (1 - similarity)
SELECT 1 - (de.embedding <=> a.embedding) AS similarity,
       a.category
FROM   dataset_embeddings de
JOIN   anchor_embeddings a ON true
WHERE  de.dataset_id = :dataset_id;
```

---

### 3.6 Central Agent

The central agent is a LangGraph ReAct agent exposed via `POST /agent/chat`. It has access to three tools and uses GPT-4o with a planning-domain system prompt. Responses stream via server-sent events (SSE).

> **Model:** `gpt-4o` at `temperature=0.4`. The agent needs strong instruction-following to correctly invoke tools and produce structured policy recommendations. Temperature 0.2 makes it too literal; 0.6+ makes recommendations vague. 0.4 is the calibrated sweet spot for open-ended policy reasoning grounded in retrieved data.

#### 3.6.1 Agent Tools

| Tool name | Signature | Description |
|---|---|---|
| `get_category_scores` | `() -> dict[str, float]` | Returns all five current aggregated category scores (0–100). |
| `get_dataset_summaries` | `(category: str, limit: int) -> list[dict]` | Returns the N most recently ingested dataset summaries for a given category, ordered by cosine similarity descending. |
| `search_datasets` | `(query: str, limit: int) -> list[dict]` | Semantic search over all stored dataset summaries using pgvector cosine similarity against the query embedding. |

#### 3.6.2 Central Agent System Prompt

```
You are an expert urban planning AI assistant. You help city planners understand
their municipal data and develop evidence-based policy interventions. You have
access to tools that let you retrieve current planning scores, dataset summaries,
and perform semantic search across all ingested civic data.

When asked for a policy recommendation:
1. Call get_category_scores() to identify the weakest scoring category.
2. Call get_dataset_summaries(category) to ground your recommendation in actual
   ingested data for that category.
3. Produce a structured recommendation with:
   (a) the problem statement with cited metrics
   (b) 2–3 specific interventions grounded in the data
   (c) expected outcomes and measurable success criteria

Always cite the specific datasets and metrics that support your reasoning.
Never invent data that is not present in tool results. If you cannot find
sufficient data to support a recommendation, say so explicitly and suggest
what additional datasets should be ingested.
```

---

## 4. Scoring System

### 4.1 Category Anchor Embeddings

Each of the five categories has a hardcoded anchor text embedded once at application startup and cached in the `anchor_embeddings` table. The anchor text is crafted to represent the semantic centroid of that category's relevant civic data concepts.

| Category | Anchor text |
|---|---|
| **Housing** | Residential housing density, affordability index, rental vacancy rates, homeownership rates, social housing stock, zoning land use, eviction rates, housing cost burden percentage, new housing starts, overcrowding rates. |
| **Transportation** | Public transit ridership, commute times, road congestion index, cycling infrastructure length, pedestrian walkability scores, transit access equity, vehicle kilometres travelled, road fatality rate, electric vehicle adoption. |
| **Healthcare** | Hospital beds per capita, primary care physician density, emergency response times, infant mortality rate, life expectancy, preventable hospitalisation rates, mental health service access, vaccination coverage, chronic disease prevalence. |
| **Employment** | Unemployment rate, labour force participation, median household income, poverty rate, job density by sector, income inequality Gini coefficient, apprenticeship and skills training enrolment, living wage compliance rate. |
| **Placemaking** | Green space per capita, park access equity, cultural venue density, community centre usage, public art installations, neighbourhood satisfaction survey scores, noise pollution levels, street-level retail vitality, social cohesion index. |

### 4.2 Importance Weights (v1.0 defaults)

Weights must sum to exactly 1.0.

| Category | Weight | Rationale |
|---|---|---|
| Housing | 0.25 | Core livability driver; directly affects resident wellbeing and cost of living. |
| Employment | 0.25 | Economic base; income determines housing affordability and tax revenue. |
| Transportation | 0.20 | Mobility equity affects access to employment, healthcare, and amenities. |
| Healthcare | 0.20 | Population health outcomes reflect service equity and long-term fiscal health. |
| Placemaking | 0.10 | Quality of life indicator; lower weight reflects data scarcity in v1. |
| **TOTAL** | **1.00** | |

### 4.3 Benchmark Evaluation Functions

Each category has hardcoded benchmark thresholds derived from WHO, OECD, and UN-Habitat standards. The `benchmark_eval` function returns a float 0–1 representing how closely the dataset's extracted metrics approach the target. Where multiple metrics are present, scores are averaged.

#### 4.3.1 Housing

| Metric | Target | Scoring function |
|---|---|---|
| Housing cost burden | <30% of households spending >30% of income on housing | `max(0, 1 - (actual_pct / 30))` |
| Housing density | ≥40 units/hectare in urban core | `min(1, actual / 40)` |
| Vacancy rate | 5–8% (balanced market) | `1 - abs(actual - 6.5) / 6.5`, clamped 0–1 |
| New housing starts | ≥10 starts per 1,000 residents/year | `min(1, actual / 10)` |

#### 4.3.2 Transportation

| Metric | Target | Scoring function |
|---|---|---|
| Transit modal share | ≥50% of commuters using transit | `min(1, actual / 50)` |
| Average commute time | ≤30 minutes | `max(0, 1 - (actual - 30) / 30)` |
| Road fatality rate | ≤1 death per 10,000 vehicles (Vision Zero) | `max(0, 1 - actual / 1)` |
| Cycling modal share | ≥10% of trips by bicycle | `min(1, actual / 10)` |

#### 4.3.3 Healthcare

| Metric | Target | Scoring function |
|---|---|---|
| Hospital beds per capita | ≥3 beds per 1,000 residents (WHO) | `min(1, actual / 3)` |
| Emergency response time | ≤8 minutes (NFPA 1710) | `max(0, 1 - (actual - 8) / 8)` |
| Primary care coverage | ≥1 GP per 1,000 residents | `min(1, actual / 1)` |
| Preventable hospitalisation | ≤150 per 100,000 (OECD average) | `max(0, 1 - actual / 150)` |

#### 4.3.4 Employment

| Metric | Target | Scoring function |
|---|---|---|
| Unemployment rate | ≤4% (full employment) | `max(0, 1 - (actual - 4) / 4)` |
| Living wage compliance | ≥80% of jobs at or above living wage | `min(1, actual / 80)` |
| Labour force participation | ≥65% | `min(1, actual / 65)` |
| Gini coefficient | ≤0.30 (low inequality) | `max(0, 1 - (actual - 0.30) / 0.30)` |

#### 4.3.5 Placemaking

| Metric | Target | Scoring function |
|---|---|---|
| Green space per capita | ≥9 m² per resident (WHO) | `min(1, actual / 9)` |
| Park access | ≥85% of residents within 400m of a park | `min(1, actual / 85)` |
| Cultural venue density | ≥1 venue per 5,000 residents | `min(1, actual / (pop / 5000))` |
| Neighbourhood satisfaction | ≥75% positive responses | `min(1, actual / 75)` |

### 4.4 Score Aggregation

When multiple datasets contribute to the same category, scores are aggregated as a similarity-weighted mean. This ensures highly relevant datasets contribute more than tangentially related ones.

```python
def aggregate_category_score(datasets: list[DatasetScore]) -> float:
    """
    datasets: list of objects with .raw_score (0-100) and .similarity (0-1)
    Returns: aggregated category score 0-100
    """
    total_weight = sum(d.similarity for d in datasets)
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(d.raw_score * d.similarity for d in datasets)
    return weighted_sum / total_weight
```

---

## 5. Database Schema

### 5.1 `datasets`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | `UUID PK` | No | Auto-generated dataset identifier. |
| `created_at` | `TIMESTAMPTZ` | No | Ingestion timestamp. |
| `input_type` | `VARCHAR(16)` | No | `csv` \| `endpoint` \| `stream` |
| `source_ref` | `TEXT` | No | Filename or endpoint URL. |
| `raw_text` | `TEXT` | Yes | Fetched/uploaded content (truncated to 12k tokens). |
| `summary` | `JSONB` | Yes | Structured summary object from GPT-4o. |
| `status` | `VARCHAR(16)` | No | `pending` \| `processing` \| `complete` \| `error` |
| `error_msg` | `TEXT` | Yes | Error detail if `status = error`. |

### 5.2 `dataset_embeddings`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | `UUID PK` | No | Embedding record identifier. |
| `dataset_id` | `UUID FK` | No | References `datasets.id` (cascade delete). |
| `embed_input` | `TEXT` | No | The text string that was embedded. |
| `embedding` | `vector(384)` | No | OpenAI `text-embedding-3-small` output. |
| `model` | `VARCHAR(64)` | No | Embedding model name for traceability. |
| `created_at` | `TIMESTAMPTZ` | No | Embedding generation timestamp. |

### 5.3 `category_scores`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `id` | `UUID PK` | No | Score record identifier. |
| `dataset_id` | `UUID FK` | No | References `datasets.id`. |
| `category` | `VARCHAR(32)` | No | `housing` \| `transportation` \| `healthcare` \| `employment` \| `placemaking` |
| `cosine_similarity` | `FLOAT` | No | Cosine similarity to category anchor (0–1). |
| `benchmark_eval` | `FLOAT` | No | Benchmark evaluation result (0–1). |
| `importance_weight` | `FLOAT` | No | Category importance weight at time of scoring. |
| `final_score` | `FLOAT` | No | `benchmark_eval × similarity × importance × 100` |
| `created_at` | `TIMESTAMPTZ` | No | Score computation timestamp. |

### 5.4 `anchor_embeddings`

| Column | Type | Nullable | Description |
|---|---|---|---|
| `category` | `VARCHAR(32) PK` | No | Category name (one row per category). |
| `anchor_text` | `TEXT` | No | The hardcoded anchor text for this category. |
| `embedding` | `vector(384)` | No | Precomputed anchor embedding. |
| `updated_at` | `TIMESTAMPTZ` | No | Last time the anchor was recomputed. |

### 5.5 Indexes

```sql
-- FK lookup
CREATE INDEX ON dataset_embeddings(dataset_id);

-- ANN vector search (tune lists based on dataset count)
CREATE INDEX ON dataset_embeddings USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Scorer queries
CREATE INDEX ON category_scores(dataset_id, category);

-- Dashboard aggregation
CREATE INDEX ON category_scores(category, created_at DESC);
```

---

## 6. API Reference

### 6.1 `POST /ingest`

Accepts a multipart form with either a file upload (CSV) or an endpoint URL. Returns a `dataset_id` immediately; processing is async via Celery.

**Request**
```
Content-Type: multipart/form-data

file:          <binary CSV>        # either file or endpoint_url, not both
endpoint_url:  <string>            # full URL including scheme
label:         <string | optional> # planner-supplied label
```

**Response 202**
```json
{
  "dataset_id": "3f8a1c2e-...",
  "status": "pending",
  "message": "Dataset queued for processing."
}
```

---

### 6.2 `GET /scores`

Returns the current aggregated category scores across all processed datasets.

**Response 200**
```json
{
  "scores": {
    "housing":        74.2,
    "transportation": 61.8,
    "healthcare":     80.5,
    "employment":     55.3,
    "placemaking":    43.1
  },
  "dataset_count": 12,
  "last_updated": "2026-03-22T14:32:00Z"
}
```

---

### 6.3 `GET /datasets`

Returns paginated list of all ingested datasets.

**Query params**

| Param | Type | Default | Description |
|---|---|---|---|
| `page` | int | 1 | Page number. |
| `page_size` | int | 20 | Results per page (max 100). |
| `status` | string | — | Filter by `pending \| processing \| complete \| error`. |
| `category` | string | — | Filter to datasets with cosine similarity >0.5 for this category. |

---

### 6.4 `GET /datasets/{dataset_id}`

Returns the full summary, all category scores, and cosine similarities for a single dataset.

**Response 200**
```json
{
  "id": "3f8a1c2e-...",
  "source_ref": "housing_2025.csv",
  "status": "complete",
  "summary": {
    "title": "City of Waterloo Housing Survey 2025",
    "domain": "housing",
    "key_metrics": { "vacancy_rate": 4.2, "cost_burden_pct": 38.1 },
    "civic_relevance": "...",
    "data_quality_notes": "..."
  },
  "scores": {
    "housing":        { "final_score": 61.2, "similarity": 0.91, "benchmark_eval": 0.67 },
    "transportation": { "final_score": 4.1,  "similarity": 0.18, "benchmark_eval": 0.45 }
  }
}
```

---

### 6.5 `POST /agent/chat`

Sends a message to the central agent. Returns an SSE stream of typed events.

**Request**
```json
{
  "message": "Which category has the worst score and what should we do?",
  "history": [
    { "role": "user",      "content": "..." },
    { "role": "assistant", "content": "..." }
  ]
}
```

**Response — SSE stream**
```
data: {"type": "text",      "content": "Based on the current scores..."}
data: {"type": "tool_call", "name": "get_category_scores", "result": {...}}
data: {"type": "text",      "content": "Employment is the weakest category at 55.3..."}
data: {"type": "tool_call", "name": "get_dataset_summaries", "result": [...]}
data: {"type": "text",      "content": "Recommended interventions: ..."}
data: {"type": "done"}
```

---

## 7. Frontend Architecture

### 7.1 Dashboard Layout

The React dashboard is a single-page application with three primary zones:

- **Header bar** — city name, last-updated timestamp, `IngestForm` trigger button.
- **Score zone (top)** — five `CategoryCard` components in a responsive grid, plus a `ScoreChart` radar.
- **Data zone (middle)** — `DatasetTable` with filtering by status and category.
- **Agent zone (right sidebar)** — `AgentChat` with SSE streaming and tool call transparency.

### 7.2 Component Breakdown

#### `CategoryCard.tsx`
Displays: category name, current score (large, colour-coded), a mini sparkline of score history (last 10 ingestions), and contributing dataset count.

Score colour thresholds:
- ≥75 → green
- 50–74 → amber
- <50 → red

#### `ScoreChart.tsx`
A Recharts `RadarChart` rendering all five category scores on a pentagon, axes 0–100. A secondary dashed overlay shows scores from the previous ingestion batch for trend comparison.

#### `AgentChat.tsx`
Maintains local message history. On submit, POSTs to `/agent/chat` and opens an `EventSource` to stream tokens. `tool_call` events render as collapsible inline callouts showing what data the agent retrieved — making reasoning transparent to the planner.

#### `DatasetTable.tsx`
Paginated table of all datasets. Columns: label, source type, top category match, status badge, ingested timestamp. Clicking a row navigates to `DatasetDetail`.

#### `IngestForm.tsx`
A modal form with two modes toggled by a radio: file upload (drag-and-drop CSV) or endpoint URL input. Submits to `POST /ingest` and adds the returned `dataset_id` to a local processing queue that drives the polling logic.

### 7.3 Polling Strategy

- While any dataset is in `pending` or `processing` status: poll `GET /scores` every **5 seconds**.
- Once all datasets are `complete` or `error`: drop to every **60 seconds**.
- On tab visibility change to hidden: pause polling; resume on visibility restore.

---

## 8. Environment Configuration

All secrets and configuration are managed via environment variables, loaded by Pydantic `Settings` in `config.py`. No secrets are committed to version control.

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key for GPT-4o and embeddings. |
| `DATABASE_URL` | Yes | — | Postgres DSN: `postgresql+asyncpg://user:pass@host/db` |
| `REDIS_URL` | Yes | — | Redis DSN for Celery broker and result backend. |
| `OPENAI_EMBED_MODEL` | No | `text-embedding-3-small` | Embedding model name. |
| `OPENAI_CHAT_MODEL` | No | `gpt-4o` | Model for summariser and central agent. |
| `OPENAI_CLASSIFY_MODEL` | No | `gpt-4o-mini` | Model for classifier node. |
| `MAX_INGEST_TOKENS` | No | `12000` | Max tokens passed to summariser. |
| `CELERY_CONCURRENCY` | No | `4` | Parallel pipeline workers. |
| `CORS_ORIGINS` | No | `http://localhost:3000` | Comma-separated allowed origins. |

---

## 9. Development Roadmap

### Phase 1 — Core pipeline (Weeks 1–2)

- Docker Compose setup: Postgres + pgvector + Redis + FastAPI + Celery.
- Alembic migrations for all four tables.
- Classifier node + HTTP fetch logic.
- Summariser node with GPT-4o, `SummarySchema` validation, retry logic.
- Embedding node with pgvector storage.
- LangGraph `StateGraph` wiring all nodes end-to-end.
- `POST /ingest` and `GET /datasets` endpoints.

### Phase 2 — Scoring (Week 3)

- `anchors.py`: anchor texts + startup embedding precomputation.
- `benchmarks.py`: all five category eval functions with unit tests.
- `scorer.py`: formula implementation + aggregation.
- `GET /scores` endpoint.
- `category_scores` table population wired into Celery pipeline task.

### Phase 3 — Central agent (Week 4)

- `central_agent.py`: ReAct agent with three tools.
- `POST /agent/chat` with SSE streaming.
- `AgentChat` frontend component.

### Phase 4 — Dashboard (Week 5)

- `CategoryCard`, `ScoreChart`, `DatasetTable`, `IngestForm` components.
- Polling logic and status-aware refresh rate.
- `DatasetDetail` page with per-dataset scores and summary view.

### Phase 5 — Hardening (Week 6)

- Error state handling throughout pipeline (UI feedback for failed ingestions).
- ivfflat index tuning for vector search performance.
- Load testing: 100 concurrent ingestion requests via Locust.
- Prompt regression tests: golden-file comparison for summariser output.

---

## 10. OpenAI Cost Estimates

Estimates assume ~50 datasets ingested per week, each averaging 5,000 tokens of raw content, and ~100 agent chat queries per week.

| Operation | Model | Est. tokens/week | Est. cost/week (USD) |
|---|---|---|---|
| Classification | `gpt-4o-mini` | 50 × 500 = 25k | ~$0.01 |
| Summarisation | `gpt-4o` | 50 × 6,000 = 300k | ~$1.50 |
| Embeddings | `text-embedding-3-small` | 50 × 500 = 25k | ~$0.003 |
| Agent chat | `gpt-4o` | 100 × 2,000 = 200k | ~$1.00 |
| **TOTAL** | | | **~$2.51 / week** |

> **Cost optimisation note:** The largest cost driver is GPT-4o summarisation. If budget is constrained, `gpt-4o-mini` can be substituted for the summariser node at approximately 10x lower cost, with a moderate reduction in summary quality. Benchmark this against your golden-file regression tests before switching in production.

---

*Urban Intelligence Platform — Technical Specification v1.0*
*March 2026*
