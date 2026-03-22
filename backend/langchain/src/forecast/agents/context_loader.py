from __future__ import annotations

from pathlib import Path

from forecast.scoring.benchmarks import IMPORTANCE_WEIGHTS

SPECIALIST_CATEGORIES: tuple[str, ...] = tuple(IMPORTANCE_WEIGHTS.keys())

CONTEXT_DIR = Path(__file__).resolve().parent / "context"
CONTEXT_PATHS: dict[str, Path] = {
    category: CONTEXT_DIR / f"{category}.md"
    for category in SPECIALIST_CATEGORIES
}


def validate_category(category: str) -> str:
    if category not in CONTEXT_PATHS:
        allowed = ", ".join(SPECIALIST_CATEGORIES)
        raise ValueError(f"Unsupported category '{category}'. Expected one of: {allowed}.")
    return category


def load_category_context(category: str) -> str:
    normalized_category = validate_category(category)
    return CONTEXT_PATHS[normalized_category].read_text(encoding="utf-8").strip()
