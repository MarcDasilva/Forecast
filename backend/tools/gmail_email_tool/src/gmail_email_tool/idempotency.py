from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path

from gmail_email_tool.models import EmailRequest

LOCK_TIMEOUT_SECONDS = 30
STALE_LOCK_SECONDS = 300


def build_idempotency_key(
    request: EmailRequest,
    *,
    sender_email: str,
    recipients: tuple[str, ...],
) -> str:
    if request.idempotency_key:
        return request.idempotency_key

    hasher = hashlib.sha256()
    hasher.update(sender_email.encode("utf-8"))
    hasher.update("|".join(sorted(recipients)).encode("utf-8"))
    hasher.update(request.subject.encode("utf-8"))
    hasher.update(request.html_body.encode("utf-8"))
    if request.attachment_png_path:
        hasher.update(request.attachment_png_path.name.encode("utf-8"))
        hasher.update(request.attachment_png_path.read_bytes())
    return hasher.hexdigest()


class LocalIdempotencyStore:
    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file
        self.lock_file = state_file.with_suffix(f"{state_file.suffix}.lock")

    @contextmanager
    def locked(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.time() + LOCK_TIMEOUT_SECONDS

        while True:
            try:
                fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                if self._lock_is_stale():
                    self.lock_file.unlink(missing_ok=True)
                    continue
                if time.time() > deadline:
                    raise TimeoutError(
                        f"Timed out waiting for idempotency lock: {self.lock_file}"
                    )
                time.sleep(0.2)

        try:
            yield
        finally:
            self.lock_file.unlink(missing_ok=True)

    def was_sent(self, idempotency_key: str) -> bool:
        state = self._read_state()
        return idempotency_key in state.get("sent", {})

    def mark_sent(
        self,
        *,
        idempotency_key: str,
        subject: str,
        recipients: tuple[str, ...],
        gmail_message_id: str,
    ) -> None:
        state = self._read_state()
        sent = state.setdefault("sent", {})
        sent[idempotency_key] = {
            "subject": subject,
            "recipients": list(recipients),
            "gmail_message_id": gmail_message_id,
            "sent_at_epoch": int(time.time()),
        }
        self._write_state(state)

    def _read_state(self) -> dict:
        if not self.state_file.exists():
            return {"sent": {}}
        return json.loads(self.state_file.read_text(encoding="utf-8"))

    def _write_state(self, state: dict) -> None:
        temp_file = self.state_file.with_suffix(f"{self.state_file.suffix}.tmp")
        temp_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(temp_file, self.state_file)

    def _lock_is_stale(self) -> bool:
        if not self.lock_file.exists():
            return False
        return (time.time() - self.lock_file.stat().st_mtime) > STALE_LOCK_SECONDS

