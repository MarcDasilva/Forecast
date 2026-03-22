from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from forecast.agents.summariser import is_probably_csv


class ClassificationResult(BaseModel):
    input_type: str
    normalized_text: str


def is_probably_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def flatten_json_payload(payload: Any, prefix: str = "") -> list[str]:
    lines: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            lines.extend(flatten_json_payload(value, next_prefix))
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            next_prefix = f"{prefix}[{index}]"
            lines.extend(flatten_json_payload(value, next_prefix))
    else:
        lines.append(f"{prefix}: {payload}")
    return lines


def normalize_json_text(raw_text: str) -> str | None:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    return "\n".join(flatten_json_payload(payload))


class ClassifierService:
    async def classify_and_prepare(self, raw_input: str) -> ClassificationResult:
        stripped = raw_input.strip()
        if is_probably_url(stripped):
            fetched_text = await self._fetch_endpoint_text(stripped)
            return ClassificationResult(input_type="endpoint", normalized_text=fetched_text)

        json_text = normalize_json_text(stripped)
        if json_text is not None:
            return ClassificationResult(input_type="stream", normalized_text=json_text)

        if is_probably_csv(stripped):
            return ClassificationResult(input_type="csv", normalized_text=stripped)

        return ClassificationResult(input_type="text", normalized_text=stripped)

    async def _fetch_endpoint_text(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            return "\n".join(flatten_json_payload(response.json()))
        return response.text
