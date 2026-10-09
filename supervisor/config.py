from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import RestartPolicy, ServiceSpec


def load_services(path: str | Path) -> list[ServiceSpec]:
    source = Path(path)
    data: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
    services = data.get("services")
    if not isinstance(services, list):
        raise ValueError("configuration must contain a services array")
    result = []
    for item in services:
        if not isinstance(item, dict):
            raise ValueError("each service must be an object")
        policy = item.get("restart_policy", {})
        result.append(ServiceSpec(
            name=item["name"],
            command=tuple(item.get("command", [])),
            dependencies=tuple(item.get("dependencies", [])),
            adapter=item.get("adapter", "native"),
            health_url=item.get("health_url"),
            working_directory=item.get("working_directory"),
            environment=tuple(sorted((item.get("environment") or {}).items())),
            docker_compose_file=item.get("docker_compose_file"),
            docker_service=item.get("docker_service"),
            restart_policy=RestartPolicy(**policy),
        ))
    return result
