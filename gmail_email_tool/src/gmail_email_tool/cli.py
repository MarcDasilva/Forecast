from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gmail_email_tool.service import bootstrap_oauth, send_email


def main() -> None:
    parser = argparse.ArgumentParser(description="Send Gmail API emails from a JSON payload.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("bootstrap-oauth", help="Run the one-time OAuth consent flow.")

    send_parser = subparsers.add_parser("send", help="Send an email from a JSON payload.")
    send_parser.add_argument("--payload-file", type=Path, help="Path to a JSON payload file.")
    send_parser.add_argument(
        "--payload-json",
        help="Inline JSON payload. If omitted, the command reads JSON from stdin.",
    )

    args = parser.parse_args()

    if args.command == "bootstrap-oauth":
        print(bootstrap_oauth())
        return

    payload = _read_payload(args.payload_file, args.payload_json)
    result = send_email(payload)
    print(json.dumps(result, indent=2))


def _read_payload(payload_file: Path | None, payload_json: str | None) -> dict:
    if payload_file and payload_json:
        raise ValueError("Use either --payload-file or --payload-json, not both.")

    if payload_file:
        return json.loads(payload_file.read_text(encoding="utf-8"))

    if payload_json:
        return json.loads(payload_json)

    stdin_content = sys.stdin.read().strip()
    if not stdin_content:
        raise ValueError("Provide a payload via --payload-file, --payload-json, or stdin.")
    return json.loads(stdin_content)


if __name__ == "__main__":
    main()

