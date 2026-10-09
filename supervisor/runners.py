from __future__ import annotations

from .docker import DockerComposeAdapter, SubprocessDockerExecutor
from .models import ServiceSpec
from .process import NativeProcessRunner


class CompositeRunner:
    """Routes lifecycle calls to the adapter declared by each service."""

    def __init__(self, native: NativeProcessRunner, docker: DockerComposeAdapter | None = None):
        self.native = native
        self.docker = docker or DockerComposeAdapter(SubprocessDockerExecutor())

    def start(self, spec: ServiceSpec) -> int | str | None:
        if spec.adapter == "docker":
            return self.docker.start(spec).container_id
        if spec.adapter != "native":
            raise ValueError(f"unsupported service adapter: {spec.adapter}")
        return self.native.start(spec)

    def stop(self, spec: ServiceSpec, pid: int | str | None) -> None:
        if spec.adapter == "docker":
            self.docker.stop(spec)
            return
        if spec.adapter != "native":
            raise ValueError(f"unsupported service adapter: {spec.adapter}")
        self.native.stop(spec, pid if isinstance(pid, int) else None)

    def poll(self, spec: ServiceSpec) -> int | None:
        if spec.adapter == "docker":
            return self.docker.poll(spec)
        if spec.adapter != "native":
            raise ValueError(f"unsupported service adapter: {spec.adapter}")
        return self.native.poll(spec)

    def logs(self, spec: ServiceSpec, max_lines: int = 200) -> str:
        if spec.adapter == "docker":
            return self.docker.logs(spec, max_lines)
        if spec.adapter != "native":
            raise ValueError(f"unsupported service adapter: {spec.adapter}")
        return self.native.logs(spec, max_lines)
