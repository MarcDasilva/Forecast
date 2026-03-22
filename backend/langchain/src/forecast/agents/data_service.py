from __future__ import annotations

import re
from urllib.parse import urlparse
from typing import Any

from sqlalchemy import select, text

from forecast.config import Settings, get_settings
from forecast.db.models import Dataset, DatasetArtifact, SourceRecording
from forecast.db.session import get_session_factory
from forecast.embeddings.service import EmbeddingService
from forecast.scoring.benchmarks import IMPORTANCE_WEIGHTS
from forecast.scoring.service import ScoringService


class AgentDataService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        embedding_service: EmbeddingService | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.embedding_service = embedding_service or EmbeddingService(settings=self.settings)

    async def get_category_scores(self) -> dict[str, float]:
        session_factory = get_session_factory()
        scoring_service = ScoringService()
        async with session_factory() as session:
            scores, _, _ = await scoring_service.get_aggregated_scores(session)
        return {category: scores.get(category, 0.0) for category in IMPORTANCE_WEIGHTS}

    async def get_dataset_summaries(self, category: str, limit: int = 5) -> list[dict[str, Any]]:
        session_factory = get_session_factory()
        async with session_factory() as session:
            rows = list(
                await session.execute(
                    text(
                        """
                        SELECT
                            d.id,
                            d.source_ref,
                            d.summary,
                            cs.category,
                            cs.cosine_similarity,
                            cs.benchmark_eval,
                            cs.final_score,
                            d.created_at
                        FROM category_scores cs
                        JOIN datasets d ON d.id = cs.dataset_id
                        WHERE d.status = 'complete'
                          AND d.summary IS NOT NULL
                          AND cs.category = :category
                        ORDER BY cs.cosine_similarity DESC, d.created_at DESC
                        LIMIT :limit
                        """
                    ),
                    {"category": category, "limit": limit},
                )
            )

        return [
            {
                "id": str(row.id),
                "source_ref": row.source_ref,
                "category": row.category,
                "similarity": float(row.cosine_similarity),
                "benchmark_eval": float(row.benchmark_eval),
                "final_score": float(row.final_score),
                "summary": row.summary,
            }
            for row in rows
        ]

    async def explain_category_score(self, category: str, limit: int = 3) -> dict[str, Any]:
        session_factory = get_session_factory()
        scoring_service = ScoringService()
        async with session_factory() as session:
            return await scoring_service.explain_category_score(
                session,
                category=category,
                limit=limit,
            )

    async def search_datasets(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        query_embedding = await self.embedding_service.embed_text(query)
        vector_literal = "[" + ",".join(f"{value:.8f}" for value in query_embedding) + "]"
        session_factory = get_session_factory()
        async with session_factory() as session:
            rows = list(
                await session.execute(
                    text(
                        """
                        SELECT
                            d.id,
                            d.source_ref,
                            d.summary,
                            1 - (de.embedding <=> CAST(:query_embedding AS vector)) AS similarity
                        FROM dataset_embeddings de
                        JOIN datasets d ON d.id = de.dataset_id
                        WHERE d.status = 'complete'
                          AND d.summary IS NOT NULL
                        ORDER BY de.embedding <=> CAST(:query_embedding AS vector)
                        LIMIT :limit
                        """
                    ),
                    {"query_embedding": vector_literal, "limit": limit},
                )
            )

        return [
            {
                "id": str(row.id),
                "source_ref": row.source_ref,
                "similarity": float(row.similarity),
                "summary": row.summary,
            }
            for row in rows
        ]

    async def get_source_recording(self, query: str) -> dict[str, Any]:
        session_factory = get_session_factory()
        normalized_query = _normalize_source_text(query)
        query_tokens = _source_tokens(query)
        query_host = _extract_host(query)

        async with session_factory() as session:
            source_rows = list(
                await session.scalars(
                    select(SourceRecording)
                    .where(SourceRecording.artifact_type == "playwright_recording")
                    .order_by(SourceRecording.created_at.desc())
                    .limit(150)
                )
            )
            rows = list(
                await session.execute(
                    select(Dataset, DatasetArtifact)
                    .join(DatasetArtifact, DatasetArtifact.dataset_id == Dataset.id)
                    .where(DatasetArtifact.artifact_type == "playwright_recording")
                    .order_by(DatasetArtifact.created_at.desc(), Dataset.created_at.desc())
                    .limit(150)
                )
            )

        best_match: dict[str, Any] | None = None
        best_score = 0
        for recording in source_rows:
            score = _score_recording_candidate(
                query=normalized_query,
                query_tokens=query_tokens,
                query_host=query_host,
                source_ref=recording.source_ref,
                title=str(recording.title or ""),
                source_url=str(recording.source_url or ""),
                label=recording.label,
            )
            if score <= best_score:
                continue
            best_score = score
            best_match = {
                "dataset_id": None,
                "source_ref": recording.source_ref,
                "title": recording.title,
                "source_url": recording.source_url or "",
                "artifact_id": str(recording.id),
                "label": recording.label,
                "filename": recording.filename,
                "mime_type": recording.mime_type,
                "size_bytes": int(recording.size_bytes),
                "download_url": f"/datasets/source-recordings/{recording.id}/download",
                "created_at": recording.created_at.isoformat() if recording.created_at else None,
            }

        for dataset, artifact in rows:
            summary = dataset.summary or {}
            source_url = str((artifact.artifact_meta or {}).get("source_url") or "")
            candidate = {
                "dataset_id": str(dataset.id),
                "source_ref": dataset.source_ref,
                "title": summary.get("title"),
                "source_url": source_url,
                "artifact_id": str(artifact.id),
                "label": artifact.label,
                "filename": artifact.filename,
                "mime_type": artifact.mime_type,
                "size_bytes": int(artifact.size_bytes),
                "download_url": f"/datasets/artifacts/{artifact.id}/download",
                "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
            }
            score = _score_recording_candidate(
                query=normalized_query,
                query_tokens=query_tokens,
                query_host=query_host,
                source_ref=dataset.source_ref,
                title=str(summary.get("title") or ""),
                source_url=source_url,
                label=artifact.label,
            )
            if score > best_score:
                best_score = score
                best_match = candidate

        if best_match is None or best_score <= 0:
            return {
                "source_query": query,
                "found": False,
                "message": "No stored Playwright recording matched that source.",
            }

        return {
            "source_query": query,
            "found": True,
            "message": f"Found a stored Playwright recording for {best_match['source_ref']}.",
            "dataset": {
                "id": best_match["dataset_id"],
                "source_ref": best_match["source_ref"],
                "title": best_match["title"],
                "source_url": best_match["source_url"],
            },
            "attachment": {
                "artifact_id": best_match["artifact_id"],
                "dataset_id": best_match["dataset_id"],
                "kind": "playwright_recording",
                "label": best_match["label"],
                "filename": best_match["filename"],
                "content_type": best_match["mime_type"],
                "size_bytes": best_match["size_bytes"],
                "download_url": best_match["download_url"],
                "source_ref": best_match["source_ref"],
                "created_at": best_match["created_at"],
            },
        }


def _normalize_source_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


def _source_tokens(value: str) -> set[str]:
    return {
        token
        for token in _normalize_source_text(value).split()
        if len(token) >= 3
        and token
        not in {
            "source",
            "recording",
            "clip",
            "video",
            "dataset",
            "about",
            "show",
            "attach",
            "download",
            "playwright",
            "statistics",
            "statistic",
            "found",
            "find",
            "finding",
            "scrape",
            "scraped",
            "webscrape",
            "suggested",
            "asked",
            "using",
            "used",
            "from",
            "for",
            "with",
            "this",
            "that",
            "these",
            "those",
            "how",
            "you",
            "your",
            "the",
            "and",
            "please",
            "chat",
        }
    }


def _extract_host(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ""
    if "://" not in candidate:
        match = re.search(r"(https?://[^\s]+)", candidate, re.IGNORECASE)
        candidate = match.group(1) if match else ""
    if not candidate:
        return ""
    parsed = urlparse(candidate)
    return parsed.netloc.lower()


def _is_test_recording(source_ref: str, source_url: str, label: str) -> bool:
    normalized_values = [
        _normalize_source_text(value)
        for value in (source_ref, source_url, label)
        if value
    ]
    host = _extract_host(source_url)
    if host in {"example.com", "localhost", "127.0.0.1"}:
        return True
    return any(
        value in {"example source", "example clip source", "threaded clip source"}
        for value in normalized_values
    )


def _score_recording_candidate(
    *,
    query: str,
    query_tokens: set[str],
    query_host: str,
    source_ref: str,
    title: str,
    source_url: str,
    label: str,
) -> int:
    if _is_test_recording(source_ref, source_url, label):
        return -1000

    haystacks = [_normalize_source_text(value) for value in (source_ref, title, source_url, label) if value]
    if not haystacks:
        return 0

    score = 0
    if query_host:
        candidate_host = _extract_host(source_url)
        if candidate_host == query_host:
            score += 120
        elif query_host and candidate_host.endswith(query_host):
            score += 80

    exact_source = _normalize_source_text(source_ref)
    exact_title = _normalize_source_text(title)
    exact_label = _normalize_source_text(label)
    if query and query in {exact_source, exact_title, exact_label}:
        score += 140

    for index, haystack in enumerate(haystacks):
        if not haystack:
            continue
        is_primary_field = index == 0
        if query and query in haystack:
            score += 60 if is_primary_field else 35
        if query and haystack in query and len(haystack.split()) >= 2:
            score += 20

    if query_tokens:
        for haystack in haystacks:
            haystack_tokens = set(haystack.split())
            overlap = len(query_tokens & haystack_tokens)
            if overlap == 0:
                continue
            score += overlap * 8
            if overlap == len(query_tokens):
                score += 24
            elif overlap >= 2:
                score += 10

    if not query_host and len(query_tokens) < 1 and score < 100:
        return 0

    if not query_host and query_tokens and score < 24:
        return 0

    return score
