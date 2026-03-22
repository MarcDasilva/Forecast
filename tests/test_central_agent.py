from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from forecast.agents.central_agent import extract_tool_calls


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
        }
    ]
