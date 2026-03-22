from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse, urlsplit, urlunsplit

import httpx
from pydantic import BaseModel

from forecast.agents.summariser import is_probably_csv
from forecast.config import Settings, get_settings


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


def build_endpoint_service_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path
    if path.endswith("/query"):
        path = path[: -len("/query")]
    return urlunsplit((parts.scheme, parts.netloc, path, "f=json", ""))


def summarize_endpoint_payload(
    *,
    url: str,
    response_text: str,
    content_type: str,
    preview_chars: int,
    service_metadata_text: str | None = None,
) -> str:
    preview = response_text[:preview_chars]
    body_was_truncated = len(response_text) > preview_chars
    lines = [
        f"Source URL: {url}",
        f"Content type: {content_type or 'unknown'}",
    ]
    if service_metadata_text:
        lines.append("Source link context:")
        lines.append(service_metadata_text)
    lines.append("Response body preview:")
    lines.append(preview)
    if body_was_truncated:
        lines.append(
            f"Response body was truncated to the first {preview_chars} characters for summarisation."
        )
    return "\n".join(lines)


def summarize_service_metadata(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""

    lines: list[str] = []
    for key in ("name", "serviceDescription", "description", "geometryType", "displayField"):
        value = payload.get(key)
        if value:
            lines.append(f"{key}: {value}")

    fields = payload.get("fields")
    if isinstance(fields, list) and fields:
        field_names = [field.get("name") for field in fields if isinstance(field, dict) and field.get("name")]
        if field_names:
            lines.append(f"fields: {', '.join(field_names[:20])}")

    if "objectIdFieldName" in payload:
        lines.append(f"objectIdFieldName: {payload['objectIdFieldName']}")

    return "\n".join(lines)


class ClassifierService:
    def __init__(self, *, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

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
            service_metadata_text = await self._fetch_service_metadata_text(client, url)

        content_type = response.headers.get("content-type", "").lower()
        response_text = response.text
        return summarize_endpoint_payload(
            url=url,
            response_text=response_text,
            content_type=content_type,
            preview_chars=self.settings.endpoint_body_preview_chars,
            service_metadata_text=service_metadata_text,
        )

    async def _fetch_service_metadata_text(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> str | None:
        service_url = build_endpoint_service_url(url)
        try:
            response = await client.get(service_url)
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        try:
            payload = response.json()
        except ValueError:
            return None

        metadata_text = summarize_service_metadata(payload)
        return metadata_text or None
