from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from forecast.api.chat import router as chat_router
from forecast.api.datasets import router as datasets_router
from forecast.api.ingest import router as ingest_router
from forecast.api.scores import router as scores_router
from forecast.api.specialist_scores import router as specialist_scores_router
from forecast.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    async def healthcheck() -> dict[str, str]:
        return {"status": "ok", "environment": settings.environment}

    app.include_router(scores_router)
    app.include_router(specialist_scores_router)
    app.include_router(ingest_router)
    app.include_router(datasets_router)
    app.include_router(chat_router)

    return app


app = create_app()
