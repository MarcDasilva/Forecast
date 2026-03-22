from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional during bare local validation
    def load_dotenv() -> None:
        return None

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUBJECT = "Vision 1 Million Scorecard Healthcare Update"
DEFAULT_RECIPIENTS = (
    "levi.fleischer@gmail.com",
    "marc.dasilva@uwaterloo.ca",
    "jjcsiu@uwaterloo.ca"
)
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


@dataclass(frozen=True)
class Settings:
    sender_email: str
    client_secret_file: Path | None
    client_secret_json: str | None
    token_file: Path | None
    token_json: str | None
    log_dir: Path
    state_file: Path
    log_level: str

    @classmethod
    def from_env(cls) -> "Settings":
        sender_email = os.getenv("GMAIL_SENDER_EMAIL", "").strip()
        if not sender_email:
            raise ValueError("GMAIL_SENDER_EMAIL must be set.")

        client_secret_file = _optional_path("GMAIL_OAUTH_CLIENT_SECRET_FILE")
        client_secret_json = _optional_str("GMAIL_OAUTH_CLIENT_SECRET_JSON")
        token_file = _optional_path("GMAIL_OAUTH_TOKEN_FILE")
        token_json = _optional_str("GMAIL_OAUTH_TOKEN_JSON")

        if not client_secret_file and not client_secret_json:
            raise ValueError(
                "Set either GMAIL_OAUTH_CLIENT_SECRET_FILE or GMAIL_OAUTH_CLIENT_SECRET_JSON."
            )

        if not token_file and not token_json:
            raise ValueError("Set either GMAIL_OAUTH_TOKEN_FILE or GMAIL_OAUTH_TOKEN_JSON.")

        log_dir = _optional_path("GMAIL_EMAIL_TOOL_LOG_DIR") or (PROJECT_ROOT / "logs")
        state_file = _optional_path("GMAIL_EMAIL_TOOL_STATE_FILE") or (
            PROJECT_ROOT / "state" / "sent_emails.json"
        )
        log_level = os.getenv("GMAIL_EMAIL_TOOL_LOG_LEVEL", "INFO").strip().upper()

        return cls(
            sender_email=sender_email,
            client_secret_file=client_secret_file,
            client_secret_json=client_secret_json,
            token_file=token_file,
            token_json=token_json,
            log_dir=log_dir,
            state_file=state_file,
            log_level=log_level,
        )


def _optional_path(env_name: str) -> Path | None:
    raw_value = os.getenv(env_name, "").strip()
    if not raw_value:
        return None
    return Path(raw_value).expanduser()


def _optional_str(env_name: str) -> str | None:
    raw_value = os.getenv(env_name, "").strip()
    return raw_value or None
