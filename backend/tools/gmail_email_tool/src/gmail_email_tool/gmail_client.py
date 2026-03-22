from __future__ import annotations

import base64
import mimetypes
import re
import time
from email.message import EmailMessage

from gmail_email_tool.config import Settings
from gmail_email_tool.models import EmailRequest

TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4


def build_gmail_service(credentials):
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def send_via_gmail_api(
    *,
    settings: Settings,
    request: EmailRequest,
    recipients: tuple[str, ...],
    idempotency_key: str,
    credentials,
) -> str:
    message = _build_message(settings, request, recipients, idempotency_key)
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    attempt = 0
    while True:
        attempt += 1
        try:
            service = build_gmail_service(credentials)
            response = (
                service.users().messages().send(userId="me", body={"raw": raw_message}).execute()
            )
            return str(response["id"])
        except Exception as exc:
            if attempt >= MAX_ATTEMPTS or not _is_transient_exception(exc):
                raise
            time.sleep(min(2 ** (attempt - 1), 16))


def _build_message(
    settings: Settings,
    request: EmailRequest,
    recipients: tuple[str, ...],
    idempotency_key: str,
) -> EmailMessage:
    message = EmailMessage()
    message["To"] = ", ".join(recipients)
    message["From"] = settings.sender_email
    message["Subject"] = request.subject
    message["X-Idempotency-Key"] = idempotency_key
    message.set_content(_html_to_plain_text(request.html_body))
    message.add_alternative(request.html_body, subtype="html")

    if request.attachment_png_path:
        if not request.attachment_png_path.exists():
            raise FileNotFoundError(f"Attachment not found: {request.attachment_png_path}")
        mime_type, _ = mimetypes.guess_type(request.attachment_png_path.name)
        maintype, subtype = (mime_type or "image/png").split("/", maxsplit=1)
        message.add_attachment(
            request.attachment_png_path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=request.attachment_png_path.name,
        )

    return message


def _html_to_plain_text(html: str) -> str:
    stripped = re.sub(r"<[^>]+>", " ", html)
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped.strip() or "HTML email"


def _is_transient_exception(exc: BaseException) -> bool:
    try:
        from googleapiclient.errors import HttpError
    except ImportError:
        HttpError = None  # type: ignore[assignment]

    if HttpError and isinstance(exc, HttpError):
        return exc.resp.status in TRANSIENT_STATUS_CODES
    return isinstance(exc, (ConnectionError, TimeoutError, OSError))
