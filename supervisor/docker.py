from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import ServiceSpec


class DockerExecutor(Protocol):
    def run(self, arguments: list[str], *, cwd: str | None = None) -> tuple[int, str, str]: ...


@dataclass(frozen=True, slots=True)
class DockerResult:
    container_id: str | None
    output: str


class DockerComposeAdapter:
    """Controls one service in a Compose project through an injected CLI."""

    def __init__(self, executor: DockerExecutor):
        self.executor = executor

    def _base(self, spec: ServiceSpec) -> list[str]:
        if not spec.docker_compose_file or not spec.docker_service:
            raise ValueError(f"Docker service {spec.name!r} needs compose file and service name")
        return ["docker", "compose", "-f", spec.docker_compose_file]

    def start(self, spec: ServiceSpec) -> DockerResult:
        code, stdout, stderr = self.executor.run(self._base(spec) + ["up", "-d", spec.docker_service], cwd=spec.working_directory)
        if code != 0:
            raise RuntimeError(stderr.strip() or f"docker compose start failed for {spec.name}")
        return DockerResult(self.container_id(spec), stdout.strip())

    def stop(self, spec: ServiceSpec) -> None:
        code, _, stderr = self.executor.run(self._base(spec) + ["stop", spec.docker_service], cwd=spec.working_directory)
        if code != 0:
            raise RuntimeError(stderr.strip() or f"docker compose stop failed for {spec.name}")

    def container_id(self, spec: ServiceSpec) -> str | None:
        code, stdout, stderr = self.executor.run(self._base(spec) + ["ps", "-q", spec.docker_service], cwd=spec.working_directory)
        if code != 0:
            raise RuntimeError(stderr.strip() or f"docker compose status failed for {spec.name}")
        return stdout.strip().splitlines()[0] if stdout.strip() else None

    def poll(self, spec: ServiceSpec) -> int | None:
        return None if self.container_id(spec) else 1

    def logs(self, spec: ServiceSpec, max_lines: int = 200) -> str:
        code, stdout, stderr = self.executor.run(self._base(spec) + ["logs", "--no-log-prefix", "--tail", str(min(max(max_lines, 1), 1000)), spec.docker_service], cwd=spec.working_directory)
        if code != 0:
            raise RuntimeError(stderr.strip() or f"docker compose logs failed for {spec.name}")
        return stdout


class SubprocessDockerExecutor:
    def run(self, arguments: list[str], *, cwd: str | None = None) -> tuple[int, str, str]:
        import subprocess
        result = subprocess.run(arguments, cwd=cwd, capture_output=True, text=True, shell=False, check=False)
        return result.returncode, result.stdout, result.stderr
