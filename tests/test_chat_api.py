from __future__ import annotations

from fastapi.testclient import TestClient

from forecast.main import app


def test_chat_endpoint_exists(monkeypatch) -> None:
    async def fake_chat(self, *, message: str, history):
        return type(
            "FakeResult",
            (),
            {
                "model_dump": lambda self: {
                    "response": f"echo:{message}",
                    "tool_calls": [],
                    "reasoning_trace": [],
                    "messages": [],
                    "attachments": [],
                }
            },
        )()

    monkeypatch.setattr("forecast.api.chat.CentralAgentService.chat", fake_chat)

    client = TestClient(app)
    response = client.post("/agent/chat", json={"message": "hello", "history": []})

    assert response.status_code == 200
    assert response.json()["response"] == "echo:hello"
