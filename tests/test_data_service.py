from forecast.agents.data_service import _score_recording_candidate, _source_tokens


def test_source_tokens_drop_generic_recording_words() -> None:
    tokens = _source_tokens("show me how you found the statistics for er-watch")

    assert tokens == {"watch"}


def test_recording_score_requires_strong_match_for_vague_query() -> None:
    score = _score_recording_candidate(
        query="show me the clip for the source i suggested",
        query_tokens=_source_tokens("show me the clip for the source i suggested"),
        query_host="",
        source_ref="er-watch",
        title="Emergency Room Wait Times in Waterloo Region",
        source_url="https://www.er-watch.ca/",
        label="Playwright clip for er-watch",
    )

    assert score == 0


def test_recording_score_rejects_example_smoke_test_entries() -> None:
    score = _score_recording_candidate(
        query="example clip source",
        query_tokens=_source_tokens("example clip source"),
        query_host="",
        source_ref="Example Clip Source",
        title="Webscraped Municipal Data",
        source_url="https://example.com",
        label="Playwright clip for Example Clip Source",
    )

    assert score < 0


def test_recording_score_prefers_exact_source_match() -> None:
    score = _score_recording_candidate(
        query="how did you find the statistics for er-watch",
        query_tokens=_source_tokens("how did you find the statistics for er-watch"),
        query_host="",
        source_ref="er-watch",
        title="Emergency Room Wait Times in Waterloo Region",
        source_url="https://www.er-watch.ca/",
        label="Playwright clip for er-watch",
    )

    assert score >= 24
