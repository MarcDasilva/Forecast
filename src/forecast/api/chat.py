from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter

from forecast.agents.central_agent import CentralAgentService, ChatHistoryMessage

router = APIRouter(prefix="/agent", tags=["agent"])


class ChatRequest(BaseModel):
    message: str
    history: list[ChatHistoryMessage] = Field(default_factory=list)


@router.post("/chat")
async def post_chat(request: ChatRequest) -> dict[str, object]:
    service = CentralAgentService()
    result = await service.chat(message=request.message, history=request.history)
    return result.model_dump()
