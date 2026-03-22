from __future__ import annotations

import importlib.util
import re
from functools import lru_cache
from pathlib import Path

DEFAULT_WEBSCRAPE_FIELDS: tuple[str, ...] = (
    "current wait time",
    "status",
    "score",
    "rating",
    "vacancy rate",
    "rent",
    "unemployment rate",
    "crime rate",
    "childcare wait time",
    "green space",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache
def _load_scrape_function():
    script_path = _repo_root() / "Webscrape" / "quick_scrape.py"
    spec = importlib.util.spec_from_file_location("forecast_quick_scrape", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load scraper from {script_path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    scrape_url = getattr(module, "scrape_url", None)
    if scrape_url is None:
        raise RuntimeError("quick_scrape.py does not expose scrape_url().")
    return scrape_url


def derive_scrape_targets(
    *,
    source_url: str,
    label: str | None = None,
    scrape_targets: str | None = None,
) -> list[str]:
    explicit_targets = [
        target.strip()
        for target in (scrape_targets or "").split(",")
        if target.strip()
    ]
    if explicit_targets:
        return explicit_targets

    derived: list[str] = []
    if label and label.strip():
        derived.append(label.strip())

    path_slug = Path(source_url.rstrip("/")).name
    normalized_slug = re.sub(r"[-_]+", " ", path_slug).strip()
    if normalized_slug and normalized_slug not in derived:
        derived.append(normalized_slug)

    for field in DEFAULT_WEBSCRAPE_FIELDS:
        if field not in derived:
            derived.append(field)

    return derived


def format_scrape_payload(
    *,
    source_url: str,
    scrape_targets: list[str],
    scrape_results: dict[str, str | None],
) -> str:
    result_lines = [
        f"- {field}: {value if value is not None else 'not found'}"
        for field, value in scrape_results.items()
    ]
    return "\n".join(
        [
            "SOURCE TYPE: webscrape",
            f"SOURCE URL: {source_url}",
            f"SCRAPE TARGETS: {', '.join(scrape_targets)}",
            "SCRAPE RESULTS:",
            *result_lines,
        ]
    )


def scrape_source(
    *,
    source_url: str,
    label: str | None = None,
    scrape_targets: str | None = None,
) -> tuple[str, list[str], dict[str, str | None]]:
    targets = derive_scrape_targets(
        source_url=source_url,
        label=label,
        scrape_targets=scrape_targets,
    )
    scrape_url = _load_scrape_function()
    scrape_results = scrape_url(source_url, *targets)
    return format_scrape_payload(
        source_url=source_url,
        scrape_targets=targets,
        scrape_results=scrape_results,
    ), targets, scrape_results
