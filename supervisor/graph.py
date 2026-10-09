from __future__ import annotations

from .models import ServiceSpec


class DependencyError(ValueError):
    pass


class DependencyGraph:
    def __init__(self, services: list[ServiceSpec] | tuple[ServiceSpec, ...]):
        self._services = {service.name: service for service in services}
        if len(self._services) != len(services):
            raise DependencyError("service names must be unique")
        for service in services:
            missing = set(service.dependencies) - self._services.keys()
            if missing:
                raise DependencyError(f"{service.name!r} depends on unknown service(s): {sorted(missing)}")
        self._assert_acyclic()

    def names(self) -> tuple[str, ...]:
        return tuple(self._services)

    def get(self, name: str) -> ServiceSpec:
        try:
            return self._services[name]
        except KeyError as exc:
            raise DependencyError(f"unknown service: {name}") from exc

    def start_order(self, name: str) -> tuple[str, ...]:
        self.get(name)
        result: list[str] = []
        visited: set[str] = set()

        def visit(current: str) -> None:
            if current in visited:
                return
            for dependency in self.get(current).dependencies:
                visit(dependency)
            visited.add(current)
            result.append(current)

        visit(name)
        return tuple(result)

    def stop_order(self, name: str) -> tuple[str, ...]:
        return tuple(reversed(self.start_order(name)))

    def all_start_order(self) -> tuple[str, ...]:
        result: list[str] = []
        for name in self._services:
            for service in self.start_order(name):
                if service not in result:
                    result.append(service)
        return tuple(result)

    def all_stop_order(self) -> tuple[str, ...]:
        return tuple(reversed(self.all_start_order()))

    def _assert_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                raise DependencyError(f"dependency cycle detected at {name!r}")
            if name in visited:
                return
            visiting.add(name)
            for dependency in self.get(name).dependencies:
                visit(dependency)
            visiting.remove(name)
            visited.add(name)

        for name in self._services:
            visit(name)
