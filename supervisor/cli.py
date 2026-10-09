from __future__ import annotations

import argparse
import os
from pathlib import Path

from .config import load_services
from .graph import DependencyGraph
from .manager import Supervisor
from .process import NativeProcessRunner
from .runners import CompositeRunner
from .health import DeriverHeartbeatCheck, HealthEngine, HttpHealthCheck, JsonHeartbeatStore, OllamaHealthCheck, PostgresHealthCheck
from .audit import AuditLog
from .monitor import SupervisorMonitor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pixie Control Center supervisor")
    parser.add_argument("--config", default="supervisor.json", help="service configuration path")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate service configuration")
    api = subparsers.add_parser("serve", help="serve the local Control API")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=9765)
    api.add_argument("--control-token-file", help="read the local API token from a protected file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    services = load_services(args.config)
    graph = DependencyGraph(services)
    if args.command == "validate":
        for name in graph.names():
            print(f"{name}: start={graph.start_order(name)} stop={graph.stop_order(name)}")
        return 0

    token = os.environ.get("PIXIE_CONTROL_TOKEN")
    if args.control_token_file:
        token_path = Path(args.control_token_file)
        if not token_path.exists():
            raise SystemExit(f"control token file does not exist: {token_path}")
        token = token_path.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("PIXIE_CONTROL_TOKEN or --control-token-file is required to serve the Control API")
    from .api import create_control_app
    import uvicorn

    log_dir = Path(os.environ.get("PIXIE_SUPERVISOR_LOG_DIR", "./supervisor-logs"))
    audit = AuditLog(log_dir / "audit.jsonl")
    supervisor = Supervisor(services, CompositeRunner(NativeProcessRunner(log_dir)), audit=audit)
    supervisor.monitor = SupervisorMonitor(supervisor)
    checks = build_health_checks(services, log_dir)
    uvicorn.run(create_control_app(supervisor, access_token=token, health_engine=HealthEngine(checks), audit=audit), host=args.host, port=args.port)
    return 0


def build_health_checks(services, log_dir: Path):
    """Build precise checks for known Pixie services, with HTTP fallback."""
    import os

    checks = {}
    for service in services:
        if service.name == "ollama":
            checks[service.name] = OllamaHealthCheck(
                os.environ.get("PIXIE_OLLAMA_URL", "http://127.0.0.1:11434"),
                os.environ.get("PIXIE_EMBEDDING_MODEL", "embeddinggemma:latest"),
                int(os.environ.get("PIXIE_EMBEDDING_DIM", "768")),
            )
        elif service.name == "postgres":
            try:
                import asyncpg
                dsn = os.environ.get("PIXIE_DATABASE_DSN", "postgresql://postgres@localhost:5432/study_partner")
                async def connector(dsn=dsn):
                    return await asyncpg.connect(dsn)
                checks[service.name] = PostgresHealthCheck(connector, os.environ.get("PIXIE_DATABASE_NAME", "study_partner"))
            except ImportError:
                if service.health_url:
                    checks[service.name] = HttpHealthCheck(service.health_url)
        elif service.name == "deriver":
            checks[service.name] = DeriverHeartbeatCheck(JsonHeartbeatStore(os.environ.get("PIXIE_DERIVER_HEARTBEAT_FILE", str(log_dir / "deriver-heartbeat.json"))))
        elif service.health_url:
            checks[service.name] = HttpHealthCheck(service.health_url)
    return checks
