from __future__ import annotations

from typing import Protocol

from .graph import DependencyGraph
from .models import ServiceRecord, ServiceSpec, ServiceState


class ProcessRunner(Protocol):
    def start(self, spec: ServiceSpec) -> int | str | None: ...

    def stop(self, spec: ServiceSpec, pid: int | str | None) -> None: ...


class Supervisor:
    """Dependency-aware lifecycle coordinator with injectable adapters."""

    def __init__(self, services: list[ServiceSpec], runner: ProcessRunner, audit=None):
        self.graph = DependencyGraph(services)
        self.runner = runner
        self.records = {service.name: ServiceRecord(service) for service in services}
        self.audit = audit

    def status(self, name: str) -> ServiceRecord:
        self.graph.get(name)
        return self.records[name]

    def start(self, name: str) -> tuple[str, ...]:
        order = self.graph.start_order(name)
        started: list[str] = []
        for service_name in order:
            record = self.records[service_name]
            if record.state in {ServiceState.RUNNING, ServiceState.HEALTHY}:
                continue
            record.state = ServiceState.STARTING
            try:
                record.pid = self.runner.start(record.spec)
                record.exit_code = None
                record.last_error = None
                record.state = ServiceState.RUNNING
                started.append(service_name)
                if self.audit:
                    self.audit.record(actor="control-api", action="start", target=service_name, result="success")
            except Exception as exc:
                record.state = ServiceState.FAILED
                record.last_error = str(exc)
                if self.audit:
                    self.audit.record(actor="control-api", action="start", target=service_name, result="failed", reason=str(exc))
                raise
        return tuple(started)

    def stop(self, name: str) -> tuple[str, ...]:
        order = self.graph.stop_order(name)
        stopped: list[str] = []
        for service_name in order:
            record = self.records[service_name]
            if record.state == ServiceState.STOPPED:
                continue
            record.state = ServiceState.STOPPING
            try:
                self.runner.stop(record.spec, record.pid)
                record.pid = None
                record.state = ServiceState.STOPPED
                stopped.append(service_name)
                if self.audit:
                    self.audit.record(actor="control-api", action="stop", target=service_name, result="success")
            except Exception as exc:
                record.state = ServiceState.FAILED
                record.last_error = str(exc)
                if self.audit:
                    self.audit.record(actor="control-api", action="stop", target=service_name, result="failed", reason=str(exc))
                raise
        return tuple(stopped)

    def restart(self, name: str) -> tuple[str, ...]:
        self.stop(name)
        return self.start(name)

    def start_all(self) -> tuple[str, ...]:
        changed: list[str] = []
        for name in self.graph.all_start_order():
            changed.extend(self.start(name))
        return tuple(changed)

    def stop_all(self) -> tuple[str, ...]:
        changed: list[str] = []
        for name in self.graph.all_stop_order():
            changed.extend(self.stop(name))
        return tuple(changed)

    def restart_failed(self) -> tuple[str, ...]:
        changed: list[str] = []
        for name, record in self.records.items():
            if record.state.value in {"FAILED", "DEGRADED"}:
                changed.extend(self.restart(name))
        return tuple(changed)
