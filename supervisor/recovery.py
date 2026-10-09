from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

from .models import RestartPolicy, ServiceRecord, ServiceState


@dataclass(frozen=True, slots=True)
class RestartDecision:
    service: str
    should_restart: bool
    retry_number: int
    delay_seconds: float
    reason: str


class RecoveryPolicy:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self._attempts: dict[str, int] = {}
        self._last_failure: dict[str, float] = {}

    def record_exit(self, record: ServiceRecord, exit_code: int | None) -> RestartDecision:
        policy: RestartPolicy = record.spec.restart_policy
        attempt = self._attempts.get(record.spec.name, 0) + 1
        self._attempts[record.spec.name] = attempt
        self._last_failure[record.spec.name] = self.clock()
        record.exit_code = exit_code
        record.state = ServiceState.FAILED
        if not policy.enabled:
            return RestartDecision(record.spec.name, False, attempt, 0, "automatic restart is disabled")
        if attempt > policy.max_retries:
            return RestartDecision(record.spec.name, False, attempt, policy.delay_for(policy.max_retries), "crash loop retry limit reached")
        return RestartDecision(record.spec.name, True, attempt, policy.delay_for(attempt), "service exited unexpectedly")

    def record_healthy(self, service: str) -> None:
        self._attempts.pop(service, None)
        self._last_failure.pop(service, None)
