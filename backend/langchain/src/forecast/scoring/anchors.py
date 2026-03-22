from __future__ import annotations

from collections.abc import Sequence

from forecast.embeddings.service import EmbeddingService


ANCHOR_TEXTS: dict[str, str] = {
    "housing": (
        "Residential housing density, affordability index, rental vacancy rates, "
        "homeownership rates, social housing stock, zoning land use, eviction rates, "
        "housing cost burden percentage, new housing starts, overcrowding rates."
    ),
    "transportation": (
        "Public transit ridership, commute times, road congestion index, cycling "
        "infrastructure length, pedestrian walkability scores, transit access equity, "
        "vehicle kilometres travelled, road fatality rate, electric vehicle adoption."
    ),
    "healthcare": (
        "Hospital beds per capita, primary care physician density, emergency response "
        "times, infant mortality rate, life expectancy, preventable hospitalisation "
        "rates, mental health service access, vaccination coverage, chronic disease prevalence."
    ),
    "employment": (
        "Unemployment rate, labour force participation, median household income, "
        "poverty rate, job density by sector, income inequality Gini coefficient, "
        "apprenticeship and skills training enrolment, living wage compliance rate."
    ),
    "placemaking": (
        "Green space per capita, park access equity, cultural venue density, "
        "community centre usage, public art installations, neighbourhood satisfaction "
        "survey scores, noise pollution levels, street-level retail vitality, social cohesion index."
    ),
}


def get_anchor_categories() -> Sequence[str]:
    return tuple(ANCHOR_TEXTS.keys())


async def build_anchor_embeddings(
    embedding_service: EmbeddingService,
) -> list[tuple[str, str, list[float], str]]:
    results: list[tuple[str, str, list[float], str]] = []
    for category, anchor_text in ANCHOR_TEXTS.items():
        embedding = await embedding_service.embed_text(anchor_text)
        results.append((category, anchor_text, embedding, embedding_service.settings.openai_embed_model))
    return results
