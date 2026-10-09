from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BackupStatus:
    state: str
    reason: str
    last_success_at: float | None = None
    artifact: str | None = None


class FileBackupStatus:
    """Reads a backup manifest written by the deployment backup job."""

    def __init__(self, manifest_path: str | Path, *, max_age_seconds: float = 86400):
        self.manifest_path = Path(manifest_path)
        self.max_age_seconds = max_age_seconds

    def status(self) -> BackupStatus:
        if not self.manifest_path.exists():
            return BackupStatus("UNKNOWN", "no backup manifest has been recorded")
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            timestamp = float(payload["last_success_at"])
            artifact = str(payload.get("artifact", "")) or None
        except (OSError, ValueError, TypeError, KeyError) as exc:
            return BackupStatus("FAILED", f"backup manifest is invalid: {exc}")
        age = time.time() - timestamp
        if age > self.max_age_seconds:
            return BackupStatus("DEGRADED", f"last backup is {round(age / 3600, 1)} hours old", timestamp, artifact)
        return BackupStatus("HEALTHY", "recent backup recorded", timestamp, artifact)
