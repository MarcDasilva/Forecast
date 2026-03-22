from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langsmith import traceable
from pydantic import BaseModel, Field, ValidationError

from forecast.agents.data_service import AgentDataService
from forecast.config import Settings, get_settings

CENTRAL_AGENT_SYSTEM_PROMPT = """
You are an expert urban planning AI assistant. You help city planners understand
their municipal data and develop evidence-based policy interventions. You have
access to tools that let you retrieve current planning scores, dataset summaries,
and perform semantic search across all ingested civic data.

When asked for a policy recommendation:
1. Call get_category_scores() to identify the weakest scoring category.
2. Call explain_category_score(category) for the focus category so you can explain how the score was produced.
3. Call get_dataset_summaries(category, limit) to ground your recommendation in actual
   ingested data for that category.
4. Produce a structured recommendation with:
   (a) the problem statement with cited metrics
   (b) 2-3 specific interventions grounded in the data
   (c) expected outcomes and measurable success criteria

Always cite the specific datasets and metrics that support your reasoning.
Never invent data that is not present in tool results. If you cannot find
sufficient data to support a recommendation, say so explicitly and suggest
what additional datasets should be ingested.

When the user asks why a category score is high or low, how a score was calculated,
or asks you to explain scoring, call explain_category_score(category) and summarize:
- the dataset score formula
- the category aggregation formula
- the top contributing datasets
- the benchmark metric components that raised or lowered the score

When the user asks about a specific source, dataset, web scrape, recording, clip,
or wants to inspect the captured source evidence, call get_source_recording(source_query).
Pass the exact source name or URL from the conversation when it is available.
If a recording is found, say that the clip is attached for download.
Do not paste or invent attachment URLs in the response body.
""".strip()


class ChatHistoryMessage(BaseModel):
    role: str
    content: str


class AgentChatResult(BaseModel):
    response: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_trace: list[dict[str, Any]] = Field(default_factory=list)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list["ChatAttachment"] = Field(default_factory=list)


class ChatAttachment(BaseModel):
    artifact_id: str
    dataset_id: str | None = None
    kind: str
    label: str
    filename: str
    content_type: str
    size_bytes: int | None = None
    download_url: str
    source_ref: str | None = None
    created_at: str | None = None


def _parse_tool_result(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _serialize_message(message: BaseMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": message.type,
        "content": message.content,
    }
    if isinstance(message, AIMessage) and message.tool_calls:
        payload["tool_calls"] = message.tool_calls
    if isinstance(message, ToolMessage):
        payload["name"] = message.name
        payload["tool_call_id"] = message.tool_call_id
    return payload


def extract_tool_calls(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    tool_results: dict[str, Any] = {}
    extracted: list[dict[str, Any]] = []

    for message in messages:
        if isinstance(message, ToolMessage):
            tool_results[message.tool_call_id] = message.content

    for message in messages:
        if isinstance(message, AIMessage):
            for tool_call in message.tool_calls:
                extracted.append(
                    {
                        "id": tool_call.get("id"),
                        "name": tool_call.get("name"),
                        "args": tool_call.get("args"),
                        "result": tool_results.get(tool_call.get("id")),
                        "parsed_result": _parse_tool_result(tool_results.get(tool_call.get("id"))),
                    }
                )

    return extracted


def _format_tool_title(tool_name: str) -> str:
    return tool_name.replace("_", " ").title()


def _summarize_tool_call(tool_name: str, args: dict[str, Any], parsed_result: Any) -> str:
    if tool_name == "get_category_scores" and isinstance(parsed_result, dict) and parsed_result:
        lowest = min(parsed_result.items(), key=lambda item: item[1])
        highest = max(parsed_result.items(), key=lambda item: item[1])
        return (
            f"Loaded the current category scoreboard. Lowest category: {lowest[0]} ({lowest[1]:.2f}); "
            f"highest category: {highest[0]} ({highest[1]:.2f})."
        )

    if tool_name == "explain_category_score" and isinstance(parsed_result, dict):
        category = parsed_result.get("category", args.get("category", "category"))
        aggregate = parsed_result.get("aggregated_score")
        contributors = parsed_result.get("top_contributors", [])
        return (
            f"Explained how {category} scored"
            f"{f' ({aggregate:.2f})' if isinstance(aggregate, (int, float)) else ''} by tracing "
            f"{len(contributors)} top contributing datasets and their benchmark components."
        )

    if tool_name == "get_dataset_summaries" and isinstance(parsed_result, list):
        category = args.get("category", "category")
        return f"Loaded {len(parsed_result)} dataset summaries to ground the {category} response in evidence."

    if tool_name == "search_datasets" and isinstance(parsed_result, list):
        return f"Ran semantic search and found {len(parsed_result)} matching datasets."

    if tool_name == "get_source_recording" and isinstance(parsed_result, dict):
        if parsed_result.get("found") and isinstance(parsed_result.get("attachment"), dict):
            dataset = parsed_result.get("dataset") or {}
            source_ref = dataset.get("source_ref") or args.get("source_query", "source")
            return f"Matched a stored Playwright clip for {source_ref} and attached it to the chat."
        return f"No stored Playwright clip matched {args.get('source_query', 'that source')}."

    return f"Called {_format_tool_title(tool_name)}."


def build_reasoning_trace(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trace: list[dict[str, Any]] = []
    for index, tool_call in enumerate(tool_calls, start=1):
        tool_name = str(tool_call.get("name") or "tool")
        parsed_result = tool_call.get("parsed_result")
        trace.append(
            {
                "step": index,
                "tool_name": tool_name,
                "title": _format_tool_title(tool_name),
                "summary": _summarize_tool_call(
                    tool_name,
                    tool_call.get("args") or {},
                    parsed_result,
                ),
                "args": tool_call.get("args") or {},
                "result_preview": (
                    tool_call.get("result")[:600] if isinstance(tool_call.get("result"), str) else None
                ),
                "scoring_explanation": (
                    parsed_result if tool_name == "explain_category_score" and isinstance(parsed_result, dict) else None
                ),
            }
        )
    return trace


def _attachment_candidates(parsed_result: Any) -> list[dict[str, Any]]:
    if isinstance(parsed_result, dict):
        candidates: list[dict[str, Any]] = []
        attachment = parsed_result.get("attachment")
        attachments = parsed_result.get("attachments")
        if isinstance(attachment, dict):
            candidates.append(attachment)
        if isinstance(attachments, list):
            candidates.extend(item for item in attachments if isinstance(item, dict))
        return candidates
    return []


def build_chat_attachments(tool_calls: list[dict[str, Any]]) -> list[ChatAttachment]:
    seen: set[str] = set()
    attachments: list[ChatAttachment] = []
    for tool_call in tool_calls:
        for candidate in _attachment_candidates(tool_call.get("parsed_result")):
            try:
                attachment = ChatAttachment.model_validate(candidate)
            except ValidationError:
                continue
            dedupe_key = attachment.artifact_id or attachment.download_url
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            attachments.append(attachment)
    return attachments


class CentralAgentService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        data_service: AgentDataService | None = None,
        agent: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.settings.configure_langsmith()
        self.data_service = data_service or AgentDataService(settings=self.settings)
        self.agent = agent or self._build_agent()

    def _build_agent(self):
        model = ChatOpenAI(
            model=self.settings.openai_chat_model,
            temperature=0.4,
            api_key=self.settings.openai_api_key_value(),
        )

        @tool
        async def get_category_scores() -> dict[str, float]:
            """Return the current aggregated score for each planning category."""
            return await self.data_service.get_category_scores()

        @tool
        async def get_dataset_summaries(category: str, limit: int = 5) -> list[dict[str, Any]]:
            """Return the top dataset summaries for a category ordered by similarity."""
            return await self.data_service.get_dataset_summaries(category, limit)

        @tool
        async def explain_category_score(category: str, limit: int = 3) -> dict[str, Any]:
            """Explain how a category score was calculated, including formulas and top contributors."""
            return await self.data_service.explain_category_score(category, limit)

        @tool
        async def search_datasets(query: str, limit: int = 5) -> list[dict[str, Any]]:
            """Perform semantic search across stored dataset summaries."""
            return await self.data_service.search_datasets(query, limit)

        @tool
        async def get_source_recording(source_query: str) -> dict[str, Any]:
            """Return a stored Playwright recording for the source or dataset that best matches the query."""
            return await self.data_service.get_source_recording(source_query)

        return create_react_agent(
            model=model,
            tools=[
                get_category_scores,
                explain_category_score,
                get_dataset_summaries,
                search_datasets,
                get_source_recording,
            ],
            prompt=CENTRAL_AGENT_SYSTEM_PROMPT,
            name="forecast_central_agent",
        )

    @traceable(name="central_agent_chat", run_type="chain")
    async def chat(
        self,
        *,
        message: str,
        history: list[ChatHistoryMessage] | list[dict[str, Any]] | None = None,
    ) -> AgentChatResult:
        prepared_history = []
        for item in history or []:
            parsed = item if isinstance(item, ChatHistoryMessage) else ChatHistoryMessage.model_validate(item)
            prepared_history.append((parsed.role, parsed.content))
        prepared_history.append(("user", message))

        result = await self.agent.ainvoke({"messages": prepared_history})
        messages = result.get("messages", [])
        assistant_messages = [
            msg for msg in messages if isinstance(msg, AIMessage) and not msg.tool_calls and msg.content
        ]
        response_text = assistant_messages[-1].content if assistant_messages else ""
        tool_calls = extract_tool_calls(messages)
        attachments = build_chat_attachments(tool_calls)
        normalized_response = (
            response_text if isinstance(response_text, str) else json.dumps(response_text)
        )
        if attachments and "sandbox:/" in normalized_response:
            source_ref = attachments[0].source_ref or "that source"
            normalized_response = (
                f"I found a stored Playwright clip for {source_ref}. "
                "The clip is attached below for download."
            )

        return AgentChatResult(
            response=normalized_response,
            tool_calls=tool_calls,
            reasoning_trace=build_reasoning_trace(tool_calls),
            messages=[_serialize_message(message) for message in messages],
            attachments=attachments,
        )
