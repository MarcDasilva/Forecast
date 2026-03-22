from forecast.ingest.webscrape import derive_scrape_targets, format_scrape_payload


def test_derive_scrape_targets_prefers_explicit_targets() -> None:
    targets = derive_scrape_targets(
        source_url="https://www.er-watch.ca/",
        label="WRHN Midtown",
        scrape_targets="wait time, status",
    )

    assert targets == ["wait time", "status"]


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
