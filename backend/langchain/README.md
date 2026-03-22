# Forecast LangChain Backend

This folder contains the Python backend for the Forecast project.

## Layout

- `src/forecast`: FastAPI app, LangChain agents, scoring, embeddings, and database code
- `tests/`: backend test suite
- `alembic/` and `alembic.ini`: database migrations
- `data/`: sample datasets
- `preprocessing/`: preprocessing utilities
- `BUILD_STEPS.md`: backend implementation roadmap

## Working Directory

Run Python backend commands from `backend/langchain` so paths in `pyproject.toml`, Alembic, and pytest stay aligned.
