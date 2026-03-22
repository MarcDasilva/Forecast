from forecast.ingest.webscrape import (
    ScrapeArtifact,
    ScrapeSourceResult,
    derive_scrape_targets,
    format_scrape_payload,
    scrape_source,
)


def test_derive_scrape_targets_prefers_explicit_targets() -> None:
    targets = derive_scrape_targets(
        source_url="https://www.er-watch.ca/",
        label="WRHN Midtown",
        scrape_targets='"WRHN Midtown", "WRHN Queen\'s"',
    )

    assert targets == ["WRHN Midtown", "WRHN Queen's"]


def test_derive_scrape_targets_falls_back_to_label_and_defaults() -> None:
    targets = derive_scrape_targets(
        source_url="https://example.com/childcare-wait-times",
        label="Waterloo Childcare",
    )

    assert targets[0] == "Waterloo Childcare"
    assert "childcare wait times" in targets
    assert "status" in targets


def test_format_scrape_payload_includes_results() -> None:
    payload = format_scrape_payload(
        source_url="https://www.er-watch.ca/",
        scrape_targets=["WRHN Midtown", "current wait time"],
        scrape_results={
            "WRHN Midtown": "6h 2m",
            "current wait time": "6h 2m",
        },
    )

    assert "SOURCE TYPE: webscrape" in payload
    assert "SOURCE URL: https://www.er-watch.ca/" in payload
    assert "- WRHN Midtown: 6h 2m" in payload


def test_scrape_source_includes_recording_artifact(monkeypatch) -> None:
    monkeypatch.setattr(
        "forecast.ingest.webscrape._load_scrape_function",
        lambda: (lambda url, *fields: {field: "captured" for field in fields}),
    )
    monkeypatch.setattr(
        "forecast.ingest.webscrape._record_playwright_clip",
        lambda **kwargs: type(
            "Artifact",
            (),
            {
                "artifact_type": "playwright_recording",
                "label": "Playwright clip",
                "filename": "clip.webm",
                "mime_type": "video/webm",
                "storage_path": "playwright-recordings/clip.webm",
                "size_bytes": 1024,
                "artifact_meta": {"source_url": kwargs["source_url"]},
            },
        )(),
    )

    result = scrape_source(
        source_url="https://www.er-watch.ca/",
        label="WRHN Midtown",
        scrape_targets="wait time",
    )

    assert result.targets == ["wait time"]
    assert result.results == {"wait time": "captured"}
    assert result.artifacts[0].filename == "clip.webm"


def test_scrape_source_routes_er_watch_through_dedicated_scraper(monkeypatch) -> None:
    monkeypatch.setattr(
        "forecast.ingest.webscrape._scrape_er_watch_source",
        lambda **kwargs: ScrapeSourceResult(
            raw_input="ER WATCH PAYLOAD",
            targets=["WRHN Midtown"],
            results={"WRHN Midtown": "2h 12m"},
            artifacts=[
                ScrapeArtifact(
                    artifact_type="playwright_recording",
                    label="Playwright clip for er-watch",
                    filename="er-watch.webm",
                    mime_type="video/webm",
                    storage_path="playwright-recordings/er-watch.webm",
                    size_bytes=2048,
                    artifact_meta={"source_url": kwargs["source_url"]},
                )
            ],
        ),
    )
    monkeypatch.setattr(
        "forecast.ingest.webscrape._load_scrape_function",
        lambda: (_ for _ in ()).throw(AssertionError("generic scraper should not be used")),
    )

    result = scrape_source(
        source_url="https://www.er-watch.ca/",
        label="er-watch",
        scrape_targets='"WRHN Midtown"',
    )

    assert result.raw_input == "ER WATCH PAYLOAD"
    assert result.targets == ["WRHN Midtown"]
    assert result.results == {"WRHN Midtown": "2h 12m"}
    assert result.artifacts[0].filename == "er-watch.webm"
