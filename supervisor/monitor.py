from __future__ import annotations

import asyncio
from typing import Protocol

from .manager import Supervisor
from .recovery import RecoveryPolicy
from .models import ServiceState


class PollableRunner(Protocol):
    def poll(self, spec): ...


class SupervisorMonitor:
    """Watches owned processes and schedules bounded recovery after exits."""

    def __init__(self, supervisor: Supervisor, *, recovery: RecoveryPolicy | None = None, interval_seconds: float = 2.0, sleep=asyncio.sleep):
        self.supervisor = supervisor
        self.recovery = recovery or RecoveryPolicy()
        self.interval_seconds = interval_seconds
        self.sleep = sleep
        self._task: asyncio.Task | None = None
        self._stopping = False

    async def run_once(self) -> list:
        decisions = []
        runner = self.supervisor.runner
        if not hasattr(runner, "poll"):
            return decisions
        for record in self.supervisor.records.values():
            if record.state not in {ServiceState.RUNNING, ServiceState.HEALTHY, ServiceState.DEGRADED}:
                continue
            exit_code = runner.poll(record.spec)
            if exit_code is None:
                continue
            decision = self.recovery.record_exit(record, exit_code)
            decisions.append(decision)
            if decision.should_restart:
                await self.sleep(decision.delay_seconds)
                self.supervisor.start(record.spec.name)
            else:
                record.last_error = decision.reason
        return decisions

    async def _loop(self) -> None:
        while not self._stopping:
            await self.run_once()
            await self.sleep(self.interval_seconds)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopping = False
            self._task = asyncio.create_task(self._loop(), name="pixie-supervisor-monitor")

    async def stop(self) -> None:
        self._stopping = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
