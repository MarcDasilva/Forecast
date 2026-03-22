# Forecast Build Steps

This project is being built as a backend-first, incremental system. The goal is to get the AI/data pipeline working end to end before building the Next.js frontend.

## Guiding Approach

Build in vertical slices:

1. Establish the core infrastructure.
2. Build one durable AI artifact at a time.
3. Add persistence before adding more orchestration.
4. Add scoring and retrieval before chat UX.
5. Build the frontend last, once the backend contracts are stable.

## Current Sequence

### Step 1. Embedding Foundation

Goal: create the first reusable AI primitive.

Scope:
- `uv` Python project setup
- backend package structure
- environment config
- LangSmith tracing setup
- embedding summary schema
- embedding input builder
- OpenAI embedding service through LangChain
- local tests for embedding generation logic

Status: completed

### Step 2. Postgres + pgvector Migrations and Persistence

Goal: persist datasets and embeddings instead of treating them as transient values.

Scope:
- Alembic initialization
- async Alembic environment wiring
- initial schema migration
- `datasets` table
- `dataset_embeddings` table
- `anchor_embeddings` table
- `vector` extension + vector index
- repository layer for dataset and embedding persistence
- local repository tests

Status: completed

### Step 3. Anchor Embeddings Seeding

Goal: create the five category anchor vectors used for similarity scoring.

Scope:
- define hardcoded category anchor texts
- embed anchors with the same embedding model and dimensions
- store anchors in `anchor_embeddings`
- add idempotent seed/update logic
- add a script or startup hook for re-seeding

Status: completed

### Step 4. Summariser Node

Goal: convert raw dataset content into structured civic summaries.

Scope:
- define `SummarySchema`
- implement summariser prompt
- use LangChain structured output
- add retry handling for malformed model responses
- validate and normalize summary payloads
- trace summariser runs in LangSmith

Status: completed

### Step 5. LangGraph Pipeline Wiring

Goal: orchestrate the ingestion pipeline as a graph.

Scope:
- define `PipelineState`
- add graph nodes
- classifier node
- fetch/normalize node behavior
- summariser node integration
- embedding node integration
- error propagation through graph state
- LangSmith tracing for graph execution

Status: completed

### Step 6. Scoring Engine and `GET /scores`

Goal: compute per-category and aggregate planning scores.

Scope:
- anchor similarity queries with pgvector
- benchmark evaluation functions
- category importance weights
- per-dataset score calculation
- aggregate category score calculation
- `category_scores` table
- `GET /scores` endpoint
- scoring unit tests

Status: completed

### Step 7. Async Ingestion API + Celery Task

Goal: make ingestion asynchronous and production-shaped.

Scope:
- `POST /ingest`
- create dataset record on submit
- enqueue Celery job
- `GET /datasets`
- `GET /datasets/{id}`
- status transitions: `pending`, `processing`, `complete`, `error`
- Redis integration for Celery

Status: completed

### Step 8. Central Agent + LangSmith-Traced Tools

Goal: support planner-facing policy analysis over stored data.

Scope:
- central agent system prompt
- tool: `get_category_scores`
- tool: `get_dataset_summaries`
- tool: `search_datasets`
- agent orchestration with LangChain/LangGraph
- SSE chat endpoint
- LangSmith traces for tool and agent runs

Status: completed

### Step 9. Next.js Frontend

Goal: build the planner dashboard after the backend is stable.

Scope:
- Next.js app scaffold
- dashboard layout
- ingest form
- score cards
- radar chart
- dataset table
- dataset detail page
- agent chat panel
- polling strategy

Status: pending

### Step 10. Hardening and Production Readiness

Goal: improve reliability, test coverage, and performance.

Scope:
- prompt regression tests
- error-state UX and API handling
- vector index tuning
- seed scripts
- load testing
- deployment configuration
- observability cleanup

Status: pending

## What Has Been Built So Far

Implemented already:
- Python backend scaffold with `uv`
- LangSmith-ready environment configuration
- FastAPI app skeleton
- embedding service with `384`-dim vectors
- traced embedding test script
- SQLAlchemy models
- Alembic setup
- initial Postgres/pgvector migration
- repository layer for datasets and embeddings
- unit tests for embeddings and repository validation

## Immediate Next Move

Build Step 9:
- scaffold the Next.js frontend
- connect ingest, scores, datasets, and chat APIs
- build dashboard, tables, charts, and chat UI
