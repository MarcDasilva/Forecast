from __future__ import annotations

import asyncio

from forecast.db.repositories import AnchorRepository
from forecast.db.session import get_session_factory
from forecast.embeddings.service import EmbeddingService
from forecast.scoring.anchors import build_anchor_embeddings


async def main() -> None:
    session_factory = get_session_factory()
    embedding_service = EmbeddingService()
    anchor_repository = AnchorRepository()

    async with session_factory() as session:
        async with session.begin():
            anchors = await build_anchor_embeddings(embedding_service)
            for category, anchor_text, embedding, _model in anchors:
                await anchor_repository.upsert_anchor_embedding(
                    session,
                    category=category,
                    anchor_text=anchor_text,
                    embedding=embedding,
                )

        stored_anchors = await anchor_repository.list_anchor_embeddings(session)
        print(f"stored={len(stored_anchors)}")
        for anchor in stored_anchors:
            print(f"{anchor.category}:{len(anchor.embedding)}")


if __name__ == "__main__":
    asyncio.run(main())
