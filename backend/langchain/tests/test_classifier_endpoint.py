from __future__ import annotations

from forecast.agents.classifier import (
    build_endpoint_service_url,
    summarize_endpoint_payload,
    summarize_service_metadata,
)


def test_build_endpoint_service_url_strips_query_suffix() -> None:
    url = (
        "https://example.com/arcgis/rest/services/Hospitals/FeatureServer/0/query"
        "?where=1%3D1&f=json"
    )
    assert (
        build_endpoint_service_url(url)
        == "https://example.com/arcgis/rest/services/Hospitals/FeatureServer/0?f=json"
    )


def test_summarize_endpoint_payload_caps_body_preview() -> None:
    summary = summarize_endpoint_payload(
        url="https://example.com/query",
        response_text="a" * 500,
        content_type="application/json",
        preview_chars=300,
        service_metadata_text="name: Hospitals",
    )

    assert "name: Hospitals" in summary
    assert "a" * 300 in summary
    assert "a" * 301 not in summary
    assert "truncated to the first 300 characters" in summary


def test_summarize_service_metadata_extracts_core_fields() -> None:
    text = summarize_service_metadata(
        {
            "name": "Hospitals",
            "serviceDescription": "Hospital locations",
            "fields": [{"name": "OBJECTID"}, {"name": "LANDMARK"}],
            "objectIdFieldName": "OBJECTID",
        }
    )

    assert "name: Hospitals" in text
    assert "serviceDescription: Hospital locations" in text
    assert "fields: OBJECTID, LANDMARK" in text
