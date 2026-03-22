# Gmail Email Tool

Standalone Python module for sending HTML emails through the Gmail API with:

- OAuth for a personal Gmail account
- local token persistence
- hardcoded recipient configuration
- optional PNG attachment
- retry handling for transient failures
- file-based idempotency to prevent duplicate sends
- rotating log files for success and failure tracking

## Project structure

```text
gmail_email_tool/
├── .env.example
├── payload.example.json
├── pyproject.toml
├── README.md
├── logs/
├── secrets/
├── src/
│   └── gmail_email_tool/
│       ├── __init__.py
│       ├── auth.py
│       ├── cli.py
│       ├── config.py
│       ├── gmail_client.py
│       ├── idempotency.py
│       ├── logging_utils.py
│       ├── models.py
│       └── service.py
├── state/
└── tests/
    └── test_service.py
```

## What the AI should call

The core callable is `send_email(payload: dict)` in [service.py](C:/Users/jerem/Forecast/backend/tools/gmail_email_tool/src/gmail_email_tool/service.py).

Accepted payload shape:

```json
{
  "subject": "Vision 1 Million Scorecard Healthcare Update",
  "html_body": "<html><body><p>Hello</p></body></html>",
  "attachment_png_path": "C:/path/to/file.png",
  "idempotency_key": "optional-stable-key"
}
```

- `subject` is optional. If omitted, the default subject is used.
- `html_body` is required.
- `attachment_png_path` is optional and must point to a `.png` file if present.
- `idempotency_key` is optional. If omitted, the tool computes one from the email content and attachment.

Recipients are intentionally not supplied by the payload. They are defined in [config.py](C:/Users/jerem/Forecast/backend/tools/gmail_email_tool/src/gmail_email_tool/config.py) as a hardcoded allowlist.

## Setup instructions

1. Create OAuth credentials in Google Cloud for a Desktop app and enable the Gmail API.
2. Copy `.env.example` to `.env`.
3. Save your Google OAuth client secret JSON locally, for example at `backend/tools/gmail_email_tool/secrets/client_secret.json`.
4. Edit [config.py](C:/Users/jerem/Forecast/backend/tools/gmail_email_tool/src/gmail_email_tool/config.py) and replace the placeholder recipients.
5. Install dependencies:

```bash
cd gmail_email_tool
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

6. Run the one-time OAuth bootstrap:

```bash
gmail-email-tool bootstrap-oauth
```

That flow opens a browser once, authorizes the Gmail account, and saves a refreshable token locally to `GMAIL_OAUTH_TOKEN_FILE`. After that, the tool can send email without repeating manual consent unless the token is revoked or the OAuth app changes.

## Local testing

Send a real email from a JSON payload file:

```bash
gmail-email-tool send --payload-file payload.example.json
```

Or pipe JSON directly:

```bash
Get-Content payload.example.json | gmail-email-tool send
```

Run unit tests:

```bash
pytest
```

## Deployment guidance

For local deployment on your machine:

1. Keep `client_secret.json` and `token.json` outside version control.
2. Set the `.env` file and ensure the paths point to local secret files.
3. Install the package in a dedicated virtual environment.
4. Call the module from your AI integration by importing `send_email` or by invoking the CLI with JSON.

Recommended import usage:

```python
from gmail_email_tool.service import send_email

result = send_email(
    {
        "subject": "Vision 1 Million Scorecard Healthcare Update",
        "html_body": "<html><body><p>Hello</p></body></html>",
        "attachment_png_path": "C:/path/to/report.png",
        "idempotency_key": "vision-1m-2026-03"
    }
)
```

## Monitoring and debugging

Logs are written to the directory configured by `GMAIL_EMAIL_TOOL_LOG_DIR`.

- `gmail_email_tool.log` records send attempts, skips, and failures.
- `state/sent_emails.json` stores successful idempotency keys and send metadata.

To inspect logs on Windows PowerShell:

```powershell
Get-Content .\logs\gmail_email_tool.log -Tail 100
```

## Common failure points and fixes

- `missing OAuth credentials`: confirm `GMAIL_OAUTH_CLIENT_SECRET_FILE` or `GMAIL_OAUTH_CLIENT_SECRET_JSON` is set correctly.
- `invalid_grant` or refresh failures: delete the local token file and rerun `gmail-email-tool bootstrap-oauth`.
- `recipient placeholders still configured`: update `DEFAULT_RECIPIENTS` in [config.py](C:/Users/jerem/Forecast/backend/tools/gmail_email_tool/src/gmail_email_tool/config.py).
- `attachment rejected`: make sure the file exists and ends with `.png`.
- `duplicate send skipped`: either use a new `idempotency_key` for a genuinely new send or change the content enough for a new computed fingerprint.
- `insufficient Gmail permissions`: verify the token includes `https://www.googleapis.com/auth/gmail.send`.
