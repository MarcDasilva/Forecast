from __future__ import annotations

import importlib.util
import logging
import re
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from forecast.config import get_settings

logger = logging.getLogger(__name__)
ER_WATCH_HOSTS = {"er-watch.ca", "www.er-watch.ca"}
ER_WATCH_DEFAULT_LOCATION = "Waterloo"

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


@dataclass(slots=True)
class ScrapeArtifact:
    artifact_type: str
    label: str
    filename: str
    mime_type: str
    storage_path: str
    size_bytes: int
    artifact_meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScrapeSourceResult:
    raw_input: str
    targets: list[str]
    results: dict[str, str | None]
    artifacts: list[ScrapeArtifact] = field(default_factory=list)


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


@lru_cache
def _load_er_watch_run():
    script_path = _repo_root() / "web_scraping" / "er_watch_scraper.py"
    spec = importlib.util.spec_from_file_location("forecast_er_watch_scraper", script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load ER Watch scraper from {script_path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = getattr(module, "run", None)
    if run is None:
        raise RuntimeError("er_watch_scraper.py does not expose run().")
    return run


def _clean_scrape_target(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _is_er_watch_source(source_url: str) -> bool:
    return urlparse(source_url).netloc.lower() in ER_WATCH_HOSTS


def derive_scrape_targets(
    *,
    source_url: str,
    label: str | None = None,
    scrape_targets: str | None = None,
) -> list[str]:
    explicit_targets = [
        _clean_scrape_target(target)
        for target in (scrape_targets or "").split(",")
        if _clean_scrape_target(target)
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

    for default_field in DEFAULT_WEBSCRAPE_FIELDS:
        if default_field not in derived:
            derived.append(default_field)

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


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "webscrape-source"


def _capture_page_snippet(page: Any) -> None:
    page.wait_for_timeout(900)
    for ratio in (0.0, 0.22, 0.48, 0.78, 1.0):
        page.evaluate(
            """
            (nextRatio) => {
              const root = document.scrollingElement || document.documentElement || document.body;
              const maxScroll = Math.max(0, (root?.scrollHeight || 0) - window.innerHeight);
              window.scrollTo({ top: maxScroll * nextRatio, behavior: "smooth" });
            }
            """,
            ratio,
        )
        page.wait_for_timeout(650)
    page.evaluate("window.scrollTo({ top: 0, behavior: 'smooth' })")
    page.wait_for_timeout(600)


def _record_playwright_clip(
    *,
    source_url: str,
    label: str | None = None,
) -> ScrapeArtifact | None:
    if not source_url.startswith(("http://", "https://")):
        return None

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright is not installed in the backend environment; skipping source recording.")
        return None

    settings = get_settings()
    storage_root = settings.artifact_storage_path
    temp_video_dir = storage_root / ".playwright-tmp"
    relative_storage_path = Path("playwright-recordings") / (
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{_slugify(label or Path(source_url.rstrip('/')).name or source_url)[:60]}.webm"
    )
    final_path = storage_root / relative_storage_path

    storage_root.mkdir(parents=True, exist_ok=True)
    temp_video_dir.mkdir(parents=True, exist_ok=True)
    final_path.parent.mkdir(parents=True, exist_ok=True)

    browser = None
    context = None
    closed_context = False

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                record_video_dir=str(temp_video_dir),
                record_video_size={"width": 1280, "height": 720},
                viewport={"width": 1280, "height": 720},
            )
            page = context.new_page()
            page.goto(source_url, wait_until="domcontentloaded", timeout=30_000)
            with suppress(PlaywrightTimeoutError):
                page.wait_for_load_state("networkidle", timeout=5_000)
            _capture_page_snippet(page)
            context.close()
            closed_context = True

            if page.video is None:
                return None

            raw_video_path = Path(page.video.path())
            raw_video_path.replace(final_path)
            return ScrapeArtifact(
                artifact_type="playwright_recording",
                label=f"Playwright clip for {label or source_url}",
                filename=final_path.name,
                mime_type="video/webm",
                storage_path=str(relative_storage_path),
                size_bytes=final_path.stat().st_size,
                artifact_meta={
                    "source_url": source_url,
                    "capture_strategy": "auto_scroll",
                    "viewport": {"width": 1280, "height": 720},
                },
            )
    except (PlaywrightTimeoutError, PlaywrightError, OSError) as exc:
        logger.warning("Unable to capture Playwright recording for %s: %s", source_url, exc)
        return None
    except Exception as exc:  # pragma: no cover - defensive logging path
        logger.warning("Unexpected Playwright recording failure for %s: %s", source_url, exc)
        return None
    finally:
        if context is not None and not closed_context:
            with suppress(Exception):
                context.close()
        if browser is not None:
            with suppress(Exception):
                browser.close()


def _build_stored_playwright_artifact(
    *,
    video_path: str | Path,
    source_url: str,
    label: str | None,
    artifact_meta: dict[str, Any] | None = None,
) -> ScrapeArtifact:
    settings = get_settings()
    storage_root = settings.artifact_storage_path
    relative_storage_path = Path("playwright-recordings") / (
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{_slugify(label or Path(source_url.rstrip('/')).name or source_url)[:60]}.webm"
    )
    final_path = storage_root / relative_storage_path
    final_path.parent.mkdir(parents=True, exist_ok=True)
    raw_video_path = Path(video_path)
    raw_video_path.replace(final_path)

    return ScrapeArtifact(
        artifact_type="playwright_recording",
        label=f"Playwright clip for {label or source_url}",
        filename=final_path.name,
        mime_type="video/webm",
        storage_path=str(relative_storage_path),
        size_bytes=final_path.stat().st_size,
        artifact_meta={
            "source_url": source_url,
            **(artifact_meta or {}),
        },
    )


def _scrape_er_watch_source(
    *,
    source_url: str,
    targets: list[str],
    label: str | None = None,
) -> ScrapeSourceResult:
    hospitals = [_clean_scrape_target(target) for target in targets if _clean_scrape_target(target)]
    if not hospitals:
        raise ValueError("ER Watch scraping requires at least one hospital target.")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is required for the dedicated ER Watch scraper.") from exc

    settings = get_settings()
    temp_video_dir = settings.artifact_storage_path / ".playwright-tmp"
    temp_video_dir.mkdir(parents=True, exist_ok=True)
    er_watch_run = _load_er_watch_run()

    with sync_playwright() as playwright:
        scrape_results, video_path = er_watch_run(
            playwright,
            location=ER_WATCH_DEFAULT_LOCATION,
            hospitals=hospitals,
            url=source_url,
            video_dir=temp_video_dir,
            headless=True,
        )

    artifact = _build_stored_playwright_artifact(
        video_path=video_path,
        source_url=source_url,
        label=label,
        artifact_meta={
            "capture_strategy": "er_watch_scraper",
            "location": ER_WATCH_DEFAULT_LOCATION,
            "targets": hospitals,
        },
    )
    return ScrapeSourceResult(
        raw_input=format_scrape_payload(
            source_url=source_url,
            scrape_targets=hospitals,
            scrape_results=scrape_results,
        ),
        targets=hospitals,
        results=scrape_results,
        artifacts=[artifact],
    )


def scrape_source(
    *,
    source_url: str,
    label: str | None = None,
    scrape_targets: str | None = None,
) -> ScrapeSourceResult:
    targets = derive_scrape_targets(
        source_url=source_url,
        label=label,
        scrape_targets=scrape_targets,
    )
    if _is_er_watch_source(source_url):
        try:
            return _scrape_er_watch_source(
                source_url=source_url,
                targets=targets,
                label=label,
            )
        except Exception as exc:
            logger.warning("Dedicated ER Watch scraper failed for %s: %s", source_url, exc)

    scrape_url = _load_scrape_function()
    scrape_results = scrape_url(source_url, *targets)
    artifact = _record_playwright_clip(source_url=source_url, label=label)
    return ScrapeSourceResult(
        raw_input=format_scrape_payload(
            source_url=source_url,
            scrape_targets=targets,
            scrape_results=scrape_results,
        ),
        targets=targets,
        results=scrape_results,
        artifacts=[artifact] if artifact is not None else [],
    )
