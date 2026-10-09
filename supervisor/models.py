from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ServiceState(StrEnum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    STOPPING = "STOPPING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class RestartPolicy:
    enabled: bool = True
    max_retries: int = 5
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0

    def delay_for(self, retry_number: int) -> float:
        if retry_number < 1:
            raise ValueError("retry_number must be positive")
        return min(self.max_delay_seconds, self.base_delay_seconds * (2 ** (retry_number - 1)))


@dataclass(frozen=True, slots=True)
class ServiceSpec:
    name: str
    command: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    adapter: str = "native"
    health_url: str | None = None
    working_directory: str | None = None
    environment: tuple[tuple[str, str], ...] = ()
    docker_compose_file: str | None = None
    docker_service: str | None = None
    restart_policy: RestartPolicy = field(default_factory=RestartPolicy)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("service name cannot be empty")
        if len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError(f"service {self.name!r} contains duplicate dependencies")


@dataclass(slots=True)
class ServiceRecord:
    spec: ServiceSpec
    state: ServiceState = ServiceState.STOPPED
    pid: int | str | None = None
    exit_code: int | None = None
    restart_count: int = 0
    last_error: str | None = None
