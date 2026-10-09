from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import Protocol

import httpx

from .models import ServiceRecord, ServiceState


class HealthStatus(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class HealthResult:
    service: str
    status: HealthStatus
    reason: str
    latency_ms: float | None = None
    evidence: str | None = None


class HealthCheck(Protocol):
    async def check(self, record: ServiceRecord) -> HealthResult: ...


class HttpHealthCheck:
    def __init__(self, url: str, *, timeout_seconds: float = 3.0, client: httpx.AsyncClient | None = None):
        self.url = url
        self.timeout_seconds = timeout_seconds
        self.client = client

    async def check(self, record: ServiceRecord) -> HealthResult:
        started = monotonic()
        try:
            if self.client is None:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.get(self.url)
            else:
                response = await self.client.get(self.url, timeout=self.timeout_seconds)
            latency_ms = round((monotonic() - started) * 1000, 2)
            if 200 <= response.status_code < 300:
                return HealthResult(record.spec.name, HealthStatus.HEALTHY, "health endpoint responded", latency_ms, str(response.status_code))
            return HealthResult(record.spec.name, HealthStatus.DEGRADED, f"health endpoint returned HTTP {response.status_code}", latency_ms, str(response.status_code))
        except (httpx.HTTPError, OSError) as exc:
            latency_ms = round((monotonic() - started) * 1000, 2)
            return HealthResult(record.spec.name, HealthStatus.FAILED, f"health endpoint unavailable: {exc}", latency_ms)


class OllamaHealthCheck:
    def __init__(self, base_url: str, model: str, expected_dimensions: int, *, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.expected_dimensions = expected_dimensions
        self.client = client

    async def check(self, record: ServiceRecord) -> HealthResult:
        started = monotonic()
        try:
            owns_client = self.client is None
            client = self.client or httpx.AsyncClient(timeout=5)
            try:
                tags = await client.get(f"{self.base_url}/api/tags")
                tags.raise_for_status()
                models = {item.get("name") for item in tags.json().get("models", [])}
                if self.model not in models:
                    return HealthResult(record.spec.name, HealthStatus.DEGRADED, f"required model is missing: {self.model}", _latency(started))
                probe = await client.post(f"{self.base_url}/api/embeddings", json={"model": self.model, "prompt": "pixie health probe"})
                probe.raise_for_status()
                vector = probe.json().get("embedding")
                if not isinstance(vector, list) or len(vector) != self.expected_dimensions:
                    return HealthResult(record.spec.name, HealthStatus.FAILED, f"embedding dimension mismatch: expected {self.expected_dimensions}", _latency(started), str(len(vector) if isinstance(vector, list) else 0))
                return HealthResult(record.spec.name, HealthStatus.HEALTHY, "model and embedding probe succeeded", _latency(started), str(len(vector)))
            finally:
                if owns_client:
                    await client.aclose()
        except (httpx.HTTPError, OSError, ValueError) as exc:
            return HealthResult(record.spec.name, HealthStatus.FAILED, f"Ollama check failed: {exc}", _latency(started))


class HeartbeatStore(Protocol):
    def last_seen(self, service: str) -> float | None: ...


class JsonHeartbeatStore:
    def __init__(self, path):
        from pathlib import Path
        self.path = Path(path)

    def last_seen(self, service: str) -> float | None:
        import json
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            value = payload.get(service) if isinstance(payload, dict) else None
            return float(value) if value is not None else None
        except (OSError, ValueError, TypeError):
            return None


class DeriverHeartbeatCheck:
    def __init__(self, store: HeartbeatStore, *, max_age_seconds: float = 90):
        self.store = store
        self.max_age_seconds = max_age_seconds

    async def check(self, record: ServiceRecord) -> HealthResult:
        import time

        seen = self.store.last_seen(record.spec.name)
        if seen is None:
            return HealthResult(record.spec.name, HealthStatus.FAILED, "worker heartbeat has not been observed")
        age = time.time() - seen
        if age > self.max_age_seconds:
            return HealthResult(record.spec.name, HealthStatus.DEGRADED, f"worker heartbeat is stale ({round(age)}s old)", evidence=str(round(age, 2)))
        return HealthResult(record.spec.name, HealthStatus.HEALTHY, "worker heartbeat is current", evidence=str(round(age, 2)))


class PostgresConnection(Protocol):
    async def fetchval(self, query: str, *args): ...

    async def fetch(self, query: str, *args): ...


class PostgresHealthCheck:
    def __init__(self, connector, expected_database: str, *, require_vector: bool = True):
        self.connector = connector
        self.expected_database = expected_database
        self.require_vector = require_vector

    async def check(self, record: ServiceRecord) -> HealthResult:
        started = monotonic()
        connection = None
        try:
            connection = await self.connector()
            if await connection.fetchval("SELECT 1") != 1:
                return HealthResult(record.spec.name, HealthStatus.FAILED, "database probe did not return 1", _latency(started))
            database = await connection.fetchval("SELECT current_database()")
            if database != self.expected_database:
                return HealthResult(record.spec.name, HealthStatus.DEGRADED, f"connected to unexpected database: {database}", _latency(started), str(database))
            if self.require_vector:
                extensions = await connection.fetch("SELECT extname FROM pg_extension WHERE extname = 'vector'")
                if not extensions:
                    return HealthResult(record.spec.name, HealthStatus.DEGRADED, "database reachable, vector extension is missing", _latency(started))
            return HealthResult(record.spec.name, HealthStatus.HEALTHY, "database connection and vector checks succeeded", _latency(started), str(database))
        except Exception as exc:
            return HealthResult(record.spec.name, HealthStatus.FAILED, f"database check failed: {exc}", _latency(started))
        finally:
            if connection is not None and hasattr(connection, "close"):
                await connection.close()


def _latency(started: float) -> float:
    return round((monotonic() - started) * 1000, 2)


class HealthEngine:
    def __init__(self, checks: dict[str, HealthCheck]):
        self.checks = checks

    async def evaluate(self, record: ServiceRecord, dependencies: list[HealthResult] | tuple[HealthResult, ...] = ()) -> HealthResult:
        failed_dependencies = [item.service for item in dependencies if item.status == HealthStatus.FAILED]
        if failed_dependencies:
            result = HealthResult(record.spec.name, HealthStatus.DEGRADED, f"dependency unavailable: {', '.join(failed_dependencies)}")
        elif record.state not in {ServiceState.RUNNING, ServiceState.HEALTHY, ServiceState.DEGRADED}:
            result = HealthResult(record.spec.name, HealthStatus.UNKNOWN, f"service is {record.state.value.lower()}")
        elif record.spec.name not in self.checks:
            result = HealthResult(record.spec.name, HealthStatus.UNKNOWN, "no health check configured")
        else:
            result = await self.checks[record.spec.name].check(record)
        if result.status == HealthStatus.HEALTHY:
            record.state = ServiceState.HEALTHY
        elif result.status == HealthStatus.DEGRADED:
            record.state = ServiceState.DEGRADED
        elif result.status == HealthStatus.FAILED:
            record.state = ServiceState.FAILED
            record.last_error = result.reason
        return result
