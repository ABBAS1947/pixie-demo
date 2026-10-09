from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


SENSITIVE_NAMES = {"token", "password", "secret", "api_key", "authorization", "access_token"}


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "[REDACTED]" if key.lower() in SENSITIVE_NAMES or any(item in key.lower() for item in SENSITIVE_NAMES) else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, *, actor: str, action: str, target: str, result: str, reason: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        event = redact({"timestamp": time.time(), "actor": actor, "action": action, "target": target, "result": result, "reason": reason, "metadata": metadata or {}})
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n")

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        if limit < 1:
            return []
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()[-limit:]
        return [json.loads(line) for line in lines if line.strip()]
