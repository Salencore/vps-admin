import subprocess
from typing import Any

import docker
from docker.errors import DockerException


class DockerCollector:
    def __init__(self) -> None:
        try:
            self.client = docker.from_env()
            self.client.ping()
        except DockerException:
            self.client = None

    def list_containers(self) -> list[dict[str, Any]]:
        if self.client is None:
            return self._list_containers_cli()

        containers = []
        for container in self.client.containers.list(all=True):
            attrs = container.attrs
            health = attrs.get("State", {}).get("Health", {}).get("Status")
            containers.append(
                {
                    "id": container.short_id,
                    "name": container.name,
                    "image": attrs.get("Config", {}).get("Image", ""),
                    "status": container.status,
                    "health": health,
                    "created": attrs.get("Created"),
                    "ports": attrs.get("NetworkSettings", {}).get("Ports") or {},
                    "stats": self._safe_stats(container),
                }
            )
        return containers

    def logs(self, container_id: str, tail: int = 200) -> str:
        if self.client is None:
            return self._run_cli(["logs", "--tail", str(tail), container_id])
        container = self.client.containers.get(container_id)
        raw = container.logs(tail=tail, timestamps=True)
        return raw.decode("utf-8", errors="replace")

    def action(self, container_id: str, action: str) -> None:
        if action not in {"start", "stop", "restart"}:
            raise ValueError("Unsupported container action")
        if self.client is None:
            self._run_cli([action, container_id])
            return
        container = self.client.containers.get(container_id)
        getattr(container, action)()

    def _safe_stats(self, container: Any) -> dict[str, Any]:
        try:
            stats = container.stats(stream=False)
        except DockerException:
            return {}

        memory = stats.get("memory_stats", {})
        usage = memory.get("usage", 0)
        limit = memory.get("limit", 0)
        cpu_delta = (
            stats.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
            - stats.get("precpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
        )
        system_delta = (
            stats.get("cpu_stats", {}).get("system_cpu_usage", 0)
            - stats.get("precpu_stats", {}).get("system_cpu_usage", 0)
        )
        online_cpus = stats.get("cpu_stats", {}).get("online_cpus") or 1
        cpu_percent = 0.0
        if system_delta > 0 and cpu_delta > 0:
            cpu_percent = (cpu_delta / system_delta) * online_cpus * 100
        return {
            "cpu_percent": round(cpu_percent, 2),
            "memory_usage": usage,
            "memory_limit": limit,
            "memory_percent": round((usage / limit) * 100, 2) if limit else 0,
        }

    def _list_containers_cli(self) -> list[dict[str, Any]]:
        output = self._run_cli(["ps", "-a", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}"])
        containers = []
        for line in output.splitlines():
            parts = line.split("\t")
            if len(parts) == 4:
                containers.append(
                    {"id": parts[0], "name": parts[1], "image": parts[2], "status": parts[3], "health": None, "stats": {}}
                )
        return containers

    def _run_cli(self, args: list[str]) -> str:
        completed = subprocess.run(
            ["docker", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return completed.stdout
