from __future__ import annotations

import pytest

from forecast.config import Settings
from forecast.db.repositories import AnchorRepository, DatasetRepository


def test_validate_embedding_dimensions_accepts_expected_size() -> None:
    repository = DatasetRepository(
        settings=Settings(openai_embed_dimensions=4, langsmith_tracing=False)
    )

    repository.validate_embedding_dimensions([0.1, 0.2, 0.3, 0.4])


def test_validate_embedding_dimensions_rejects_wrong_size() -> None:
    repository = DatasetRepository(
        settings=Settings(openai_embed_dimensions=4, langsmith_tracing=False)
    )

    with pytest.raises(ValueError, match="expected 4, received 3"):
        repository.validate_embedding_dimensions([0.1, 0.2, 0.3])


def test_anchor_repository_dimension_validation_matches_dataset_repository() -> None:
    repository = AnchorRepository(
        settings=Settings(openai_embed_dimensions=2, langsmith_tracing=False)
    )

    with pytest.raises(ValueError, match="expected 2, received 1"):
        repository.validate_embedding_dimensions([0.1])
