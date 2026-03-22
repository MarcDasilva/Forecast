from __future__ import annotations

import json
from pathlib import Path

from gmail_email_tool.config import GMAIL_SEND_SCOPE, Settings


def bootstrap_oauth(settings: Settings) -> Path | None:
    creds = _run_installed_app_flow(settings)
    _persist_token(creds.to_json(), settings)
    return settings.token_file


def load_credentials(settings: Settings):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_payload = _read_json_text(
        file_path=settings.token_file,
        inline_json=settings.token_json,
        description="token",
    )
    creds = Credentials.from_authorized_user_info(json.loads(token_payload), [GMAIL_SEND_SCOPE])

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _persist_token(creds.to_json(), settings)

    if not creds.valid:
        raise ValueError(
            "Stored Gmail OAuth token is invalid. Run the bootstrap flow again to refresh it."
        )

    return creds


def _run_installed_app_flow(settings: Settings):
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_secret = _read_json_text(
        file_path=settings.client_secret_file,
        inline_json=settings.client_secret_json,
        description="client secret",
    )
    client_config = json.loads(client_secret)
    flow = InstalledAppFlow.from_client_config(client_config, [GMAIL_SEND_SCOPE])
    return flow.run_local_server(port=0)


def _persist_token(token_json: str, settings: Settings) -> None:
    if settings.token_file:
        settings.token_file.parent.mkdir(parents=True, exist_ok=True)
        settings.token_file.write_text(token_json, encoding="utf-8")


def _read_json_text(
    *,
    file_path: Path | None,
    inline_json: str | None,
    description: str,
) -> str:
    if inline_json:
        return inline_json

    if not file_path:
        raise ValueError(f"No {description} source configured.")

    if not file_path.exists():
        raise FileNotFoundError(f"{description.title()} file not found: {file_path}")

    return file_path.read_text(encoding="utf-8")

