from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from forecast.agents.central_agent import (
    build_chat_attachments,
    build_reasoning_trace,
    extract_tool_calls,
)


def test_extract_tool_calls_matches_ai_and_tool_messages() -> None:
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call-1",
                    "name": "get_category_scores",
                    "args": {},
                }
            ],
        ),
        ToolMessage(content='{"housing": 12.0}', tool_call_id="call-1", name="get_category_scores"),
    ]

    extracted = extract_tool_calls(messages)

    assert extracted == [
        {
            "id": "call-1",
            "name": "get_category_scores",
            "args": {},
            "result": '{"housing": 12.0}',
            "parsed_result": {"housing": 12.0},
        }
    ]


def test_build_reasoning_trace_includes_scoring_explanation() -> None:
    tool_calls = [
        {
            "id": "call-2",
            "name": "explain_category_score",
            "args": {"category": "housing", "limit": 3},
            "result": '{"category":"housing","aggregated_score":42.0,"top_contributors":[]}',
            "parsed_result": {
                "category": "housing",
                "aggregated_score": 42.0,
                "top_contributors": [],
            },
        }
    ]

    trace = build_reasoning_trace(tool_calls)

    assert trace == [
        {
            "step": 1,
            "tool_name": "explain_category_score",
            "title": "Explain Category Score",
            "summary": (
                "Explained how housing scored (42.00) by tracing 0 top contributing datasets "
                "and their benchmark components."
            ),
            "args": {"category": "housing", "limit": 3},
            "result_preview": '{"category":"housing","aggregated_score":42.0,"top_contributors":[]}',
            "scoring_explanation": {
                "category": "housing",
                "aggregated_score": 42.0,
                "top_contributors": [],
            },
        }
    ]


def test_build_chat_attachments_extracts_source_recording() -> None:
    tool_calls = [
        {
            "id": "call-3",
            "name": "get_source_recording",
            "args": {"source_query": "er watch"},
            "result": "",
            "parsed_result": {
                "found": True,
                "attachment": {
                    "artifact_id": "artifact-1",
                    "dataset_id": "dataset-1",
                    "kind": "playwright_recording",
                    "label": "Playwright clip for ER Watch",
                    "filename": "er-watch.webm",
                    "content_type": "video/webm",
                    "download_url": "/datasets/artifacts/artifact-1/download",
                    "source_ref": "ER Watch",
                },
            },
        }
    ]

    attachments = build_chat_attachments(tool_calls)

    assert len(attachments) == 1
    assert attachments[0].artifact_id == "artifact-1"
    assert attachments[0].download_url == "/datasets/artifacts/artifact-1/download"
