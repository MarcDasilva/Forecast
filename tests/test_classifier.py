from __future__ import annotations

from forecast.agents.classifier import ClassifierService, flatten_json_payload, normalize_json_text


def test_flatten_json_payload_produces_dot_notation_lines() -> None:
    lines = flatten_json_payload({"city": "Toronto", "metrics": {"beds": 2.8}})

    assert "city: Toronto" in lines
    assert "metrics.beds: 2.8" in lines


def test_normalize_json_text_returns_none_for_non_json() -> None:
    assert normalize_json_text("not json") is None


async def test_classifier_detects_csv_input() -> None:
    classifier = ClassifierService()
    result = await classifier.classify_and_prepare("city,beds\nToronto,2.8\n")

    assert result.input_type == "csv"
    assert "Toronto,2.8" in result.normalized_text
