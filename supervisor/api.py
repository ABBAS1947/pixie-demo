from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse

from .manager import Supervisor
from .health import HealthEngine


def create_control_app(supervisor: Supervisor, *, access_token: str, health_engine: HealthEngine | None = None, audit=None) -> FastAPI:
    if not access_token:
        raise ValueError("access_token is required")

    app = FastAPI(title="Pixie Control API", version="0.1.0")
    monitor = getattr(supervisor, "monitor", None)
    if monitor is not None:
        app.add_event_handler("startup", monitor.start)
        app.add_event_handler("shutdown", monitor.stop)

    def authorize(authorization: str | None) -> None:
        expected = f"Bearer {access_token}"
        if authorization != expected:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid control token")

    def record_payload(record):
        payload = asdict(record)
        payload["state"] = record.state.value
        payload["spec"]["restart_policy"] = asdict(record.spec.restart_policy)
        return payload

    @app.get("/health")
    async def health(authorization: str | None = Header(default=None)):
        authorize(authorization)
        return {"status": "ok", "services": len(supervisor.records)}

    @app.get("/services")
    async def services(authorization: str | None = Header(default=None)):
        authorize(authorization)
        return {"services": [record_payload(record) for record in supervisor.records.values()]}

    @app.get("/diagnostics")
    async def diagnostics(authorization: str | None = Header(default=None)):
        authorize(authorization)
        if health_engine is None:
            return {"results": [], "message": "no health engine configured"}
        results = {}
        for name in supervisor.graph.names():
            dependency_results = [results[dependency] for dependency in supervisor.status(name).spec.dependencies if dependency in results]
            result = await health_engine.evaluate(supervisor.status(name), dependency_results)
            results[name] = result
        return {"results": [{"service": result.service, "status": result.status.value, "reason": result.reason, "latency_ms": result.latency_ms, "evidence": result.evidence} for result in results.values()]}

    @app.get("/audit")
    async def audit_events(authorization: str | None = Header(default=None), limit: int = 100):
        authorize(authorization)
        if audit is None:
            return {"events": []}
        return {"events": audit.recent(min(max(limit, 1), 500))}

    @app.get("/incident-report")
    async def incident_report(authorization: str | None = Header(default=None)):
        authorize(authorization)
        diagnostics_result = await diagnostics(authorization)
        report = {
            "format": "pixie-incident-report-v1",
            "services": [record_payload(record) for record in supervisor.records.values()],
            "diagnostics": diagnostics_result.get("results", []),
            "audit": audit.recent(500) if audit is not None else [],
        }
        return JSONResponse(report, headers={"Content-Disposition": "attachment; filename=pixie-incident-report.json"})

    @app.post("/services/{name}/start")
    async def start(name: str, authorization: str | None = Header(default=None)):
        authorize(authorization)
        try:
            changed = supervisor.start(name)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"changed": changed, "service": record_payload(supervisor.status(name))}

    @app.post("/services/{name}/stop")
    async def stop(name: str, authorization: str | None = Header(default=None)):
        authorize(authorization)
        try:
            changed = supervisor.stop(name)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"changed": changed, "service": record_payload(supervisor.status(name))}

    @app.post("/services/{name}/restart")
    async def restart(name: str, authorization: str | None = Header(default=None)):
        authorize(authorization)
        try:
            changed = supervisor.restart(name)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"changed": changed, "service": record_payload(supervisor.status(name))}

    @app.get("/services/{name}/logs")
    async def logs(name: str, authorization: str | None = Header(default=None), lines: int = 200):
        authorize(authorization)
        try:
            record = supervisor.status(name)
            content = supervisor.runner.logs(record.spec, min(max(lines, 1), 1000))
        except (KeyError, ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"service": name, "lines": content.splitlines(), "truncated": len(content.splitlines()) >= min(max(lines, 1), 1000)}

    @app.post("/stack/start")
    async def start_stack(authorization: str | None = Header(default=None)):
        authorize(authorization)
        return {"changed": supervisor.start_all()}

    @app.post("/stack/stop")
    async def stop_stack(authorization: str | None = Header(default=None)):
        authorize(authorization)
        return {"changed": supervisor.stop_all()}

    @app.post("/stack/restart-failed")
    async def restart_failed(authorization: str | None = Header(default=None)):
        authorize(authorization)
        return {"changed": supervisor.restart_failed()}

    @app.get("/backup/status")
    async def backup_status(authorization: str | None = Header(default=None)):
        authorize(authorization)
        provider = getattr(supervisor, "backup_status", None)
        if provider is None:
            return {"state": "UNKNOWN", "reason": "no backup provider configured"}
        result = provider.status()
        return {"state": result.state, "reason": result.reason, "last_success_at": result.last_success_at, "artifact": result.artifact}

    return app
