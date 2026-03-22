from __future__ import annotations

import json
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langsmith import traceable
from pydantic import BaseModel, Field

from forecast.agents.data_service import AgentDataService
from forecast.config import Settings, get_settings

CENTRAL_AGENT_SYSTEM_PROMPT = """
You are an expert urban planning AI assistant. You help city planners understand
their municipal data and develop evidence-based policy interventions. You have
access to tools that let you retrieve current planning scores, dataset summaries,
and perform semantic search across all ingested civic data.

When asked for a policy recommendation:
1. Call get_category_scores() to identify the weakest scoring category.
2. Call get_dataset_summaries(category, limit) to ground your recommendation in actual
   ingested data for that category.
3. Produce a structured recommendation with:
   (a) the problem statement with cited metrics
   (b) 2-3 specific interventions grounded in the data
   (c) expected outcomes and measurable success criteria

Always cite the specific datasets and metrics that support your reasoning.
Never invent data that is not present in tool results. If you cannot find
sufficient data to support a recommendation, say so explicitly and suggest
what additional datasets should be ingested.
""".strip()


class ChatHistoryMessage(BaseModel):
    role: str
    content: str


class AgentChatResult(BaseModel):
    response: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    messages: list[dict[str, Any]] = Field(default_factory=list)


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
                    }
                )

    return extracted


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
        async def search_datasets(query: str, limit: int = 5) -> list[dict[str, Any]]:
            """Perform semantic search across stored dataset summaries."""
            return await self.data_service.search_datasets(query, limit)

        return create_agent(
            model=model,
            tools=[get_category_scores, get_dataset_summaries, search_datasets],
            system_prompt=CENTRAL_AGENT_SYSTEM_PROMPT,
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

        return AgentChatResult(
            response=response_text if isinstance(response_text, str) else json.dumps(response_text),
            tool_calls=extract_tool_calls(messages),
            messages=[_serialize_message(message) for message in messages],
        )
