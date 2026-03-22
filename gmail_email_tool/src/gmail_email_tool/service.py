from __future__ import annotations

from typing import Any, Callable

from gmail_email_tool.auth import bootstrap_oauth as run_bootstrap_oauth
from gmail_email_tool.auth import load_credentials
from gmail_email_tool.config import DEFAULT_RECIPIENTS, Settings
from gmail_email_tool.gmail_client import send_via_gmail_api
from gmail_email_tool.idempotency import LocalIdempotencyStore, build_idempotency_key
from gmail_email_tool.logging_utils import configure_logger
from gmail_email_tool.models import EmailRequest, SendResult

SendCallable = Callable[..., str]


def send_email(payload: dict[str, Any]) -> dict[str, Any]:
    settings = Settings.from_env()
    service = GmailEmailService(settings=settings)
    result = service.send(payload)
    return {
        "status": result.status,
        "idempotency_key": result.idempotency_key,
        "recipients": list(result.recipients),
        "gmail_message_id": result.gmail_message_id,
        "detail": result.detail,
    }


def bootstrap_oauth() -> str:
    settings = Settings.from_env()
    token_path = run_bootstrap_oauth(settings)
    return str(token_path) if token_path else "OAuth token loaded from environment only."


class GmailEmailService:
    def __init__(
        self,
        *,
        settings: Settings,
        sender: SendCallable = send_via_gmail_api,
        credential_loader: Callable[[Settings], Any] = load_credentials,
    ) -> None:
        self.settings = settings
        self.sender = sender
        self.credential_loader = credential_loader
        self.logger = configure_logger(settings.log_dir, settings.log_level)
        self.idempotency_store = LocalIdempotencyStore(settings.state_file)

    def send(self, payload: dict[str, Any]) -> SendResult:
        request = EmailRequest.from_payload(payload)
        recipients = self._validated_recipients()
        idempotency_key = build_idempotency_key(
            request,
            sender_email=self.settings.sender_email,
            recipients=recipients,
        )

        with self.idempotency_store.locked():
            if self.idempotency_store.was_sent(idempotency_key):
                detail = "Duplicate request skipped because this idempotency key was already sent."
                self.logger.info(
                    "Skipping duplicate send for idempotency_key=%s subject=%s",
                    idempotency_key,
                    request.subject,
                )
                return SendResult(
                    status="skipped",
                    idempotency_key=idempotency_key,
                    recipients=recipients,
                    gmail_message_id=None,
                    detail=detail,
                )

            self.logger.info(
                "Sending email idempotency_key=%s subject=%s recipients=%s",
                idempotency_key,
                request.subject,
                recipients,
            )
            try:
                credentials = self.credential_loader(self.settings)
                gmail_message_id = self.sender(
                    settings=self.settings,
                    request=request,
                    recipients=recipients,
                    idempotency_key=idempotency_key,
                    credentials=credentials,
                )
            except Exception:
                self.logger.exception(
                    "Email send failed for idempotency_key=%s subject=%s",
                    idempotency_key,
                    request.subject,
                )
                raise

            self.idempotency_store.mark_sent(
                idempotency_key=idempotency_key,
                subject=request.subject,
                recipients=recipients,
                gmail_message_id=gmail_message_id,
            )
            self.logger.info(
                "Email sent successfully idempotency_key=%s gmail_message_id=%s",
                idempotency_key,
                gmail_message_id,
            )
            return SendResult(
                status="sent",
                idempotency_key=idempotency_key,
                recipients=recipients,
                gmail_message_id=gmail_message_id,
                detail="Email sent successfully.",
            )

    def _validated_recipients(self) -> tuple[str, ...]:
        recipients = tuple(email.strip() for email in DEFAULT_RECIPIENTS if email.strip())
        if not recipients or any(email.startswith("replace-recipient-") for email in recipients):
            raise ValueError(
                "Update DEFAULT_RECIPIENTS in gmail_email_tool.config with real recipient emails."
            )
        return recipients
