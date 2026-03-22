from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gmail_email_tool.config import DEFAULT_SUBJECT


@dataclass(frozen=True)
class EmailRequest:
    subject: str
    html_body: str
    attachment_png_path: Path | None
    idempotency_key: str | None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "EmailRequest":
        if not isinstance(payload, dict):
            raise ValueError("Payload must be a JSON object.")

        subject = str(payload.get("subject") or DEFAULT_SUBJECT).strip()
        html_body = str(payload.get("html_body") or "").strip()
        if not html_body:
            raise ValueError("Payload field 'html_body' is required.")

        raw_attachment = payload.get("attachment_png_path")
        attachment_path = Path(raw_attachment).expanduser() if raw_attachment else None
        if attachment_path and attachment_path.suffix.lower() != ".png":
            raise ValueError("attachment_png_path must point to a .png file.")

        raw_idempotency_key = payload.get("idempotency_key")
        idempotency_key = str(raw_idempotency_key).strip() if raw_idempotency_key else None

        return cls(
            subject=subject,
            html_body=html_body,
            attachment_png_path=attachment_path,
            idempotency_key=idempotency_key,
        )


@dataclass(frozen=True)
class SendResult:
    status: str
    idempotency_key: str
    recipients: tuple[str, ...]
    gmail_message_id: str | None
    detail: str

