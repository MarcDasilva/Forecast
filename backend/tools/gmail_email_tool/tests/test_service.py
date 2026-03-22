from __future__ import annotations

import json
import logging
import shutil
import unittest
from pathlib import Path

from gmail_email_tool.config import Settings
from gmail_email_tool.service import GmailEmailService


class GmailEmailServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_path = Path(__file__).resolve().parent / ".tmp" / self._testMethodName
        if self.tmp_path.exists():
            shutil.rmtree(self.tmp_path)
        self.tmp_path.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        logger = logging.getLogger("gmail_email_tool")
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
        if self.tmp_path.exists():
            shutil.rmtree(self.tmp_path)

    def test_duplicate_send_is_skipped(self) -> None:
        settings = self._make_settings()
        sent_ids: list[str] = []

        def fake_sender(**kwargs) -> str:
            sent_ids.append(kwargs["idempotency_key"])
            return "gmail-message-123"

        service = GmailEmailService(
            settings=settings,
            sender=fake_sender,
            credential_loader=lambda _: object(),
        )
        service._validated_recipients = lambda: ("recipient@example.com",)  # type: ignore[method-assign]

        payload = {
            "subject": "Vision 1 Million Scorecard Healthcare Update",
            "html_body": "<p>Hello</p>",
            "idempotency_key": "stable-key",
        }

        first = service.send(payload)
        second = service.send(payload)

        self.assertEqual(first.status, "sent")
        self.assertEqual(second.status, "skipped")
        self.assertEqual(sent_ids, ["stable-key"])

    def test_sent_state_file_is_written(self) -> None:
        settings = self._make_settings()
        service = GmailEmailService(
            settings=settings,
            sender=lambda **kwargs: "gmail-message-456",
            credential_loader=lambda _: object(),
        )
        service._validated_recipients = lambda: ("recipient@example.com",)  # type: ignore[method-assign]

        result = service.send({"html_body": "<p>Body</p>", "idempotency_key": "abc"})

        state = json.loads(settings.state_file.read_text(encoding="utf-8"))
        self.assertEqual(result.status, "sent")
        self.assertEqual(state["sent"]["abc"]["gmail_message_id"], "gmail-message-456")

    def _make_settings(self) -> Settings:
        return Settings(
            sender_email="sender@example.com",
            client_secret_file=self.tmp_path / "client_secret.json",
            client_secret_json='{"installed":{"client_id":"abc","client_secret":"def"}}',
            token_file=self.tmp_path / "token.json",
            token_json='{"token":"x","refresh_token":"y","token_uri":"https://oauth2.googleapis.com/token","client_id":"abc","client_secret":"def","scopes":["https://www.googleapis.com/auth/gmail.send"]}',
            log_dir=self.tmp_path / "logs",
            state_file=self.tmp_path / "state" / "sent_emails.json",
            log_level="INFO",
        )


if __name__ == "__main__":
    unittest.main()
