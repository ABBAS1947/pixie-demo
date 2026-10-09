from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .models import ServiceSpec


class NativeProcessRunner:
    """Owns native child processes without invoking a shell."""

    def __init__(self, log_directory: str | Path):
        self.log_directory = Path(log_directory)
        self.log_directory.mkdir(parents=True, exist_ok=True)
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._handles: dict[str, tuple[object, object]] = {}

    def start(self, spec: ServiceSpec) -> int:
        existing = self._processes.get(spec.name)
        if existing is not None and existing.poll() is None:
            return existing.pid

        if not spec.command:
            raise ValueError(f"service {spec.name!r} has no command")
        stdout_path = self.log_directory / f"{spec.name}.stdout.log"
        stderr_path = self.log_directory / f"{spec.name}.stderr.log"
        stdout = stdout_path.open("ab")
        stderr = stderr_path.open("ab")
        environment = os.environ.copy()
        environment.update(dict(spec.environment))
        try:
            process = subprocess.Popen(
                list(spec.command),
                cwd=spec.working_directory,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                shell=False,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except Exception:
            stdout.close()
            stderr.close()
            raise
        self._processes[spec.name] = process
        self._handles[spec.name] = (stdout, stderr)
        return process.pid

    def stop(self, spec: ServiceSpec, pid: int | None) -> None:
        process = self._processes.get(spec.name)
        if process is None or process.poll() is not None:
            self._close_logs(spec.name)
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        self._close_logs(spec.name)

    def poll(self, spec: ServiceSpec) -> int | None:
        process = self._processes.get(spec.name)
        if process is None:
            return None
        code = process.poll()
        if code is not None:
            self._close_logs(spec.name)
        return code

    def _close_logs(self, name: str) -> None:
        handles = self._handles.pop(name, None)
        if handles:
            for handle in handles:
                handle.close()

    def logs(self, spec: ServiceSpec, max_lines: int = 200) -> str:
        if max_lines < 1:
            return ""
        path = self.log_directory / f"{spec.name}.stdout.log"
        if not path.exists():
            return ""
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-min(max_lines, 1000):])
