import asyncio
import logging
from collections import Counter

from .collectors.docker import DockerCollector
from .collectors.security import read_auth_events
from .collectors.system import get_overview
from .config import get_settings
from .db import add_security_event, get_setting
from .notifier import Notifier

logger = logging.getLogger(__name__)


class Monitor:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.docker = DockerCollector()
        self.notifier = Notifier()
        self.security_bootstrapped = False

    async def run_forever(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:
                logger.exception("Monitor tick failed")
            await asyncio.sleep(self.settings.poll_interval_seconds)

    async def tick(self) -> None:
        overview = get_overview()
        await self._check_resource_alerts(overview)
        await self._check_containers()
        await self._check_security_events()

    async def _check_resource_alerts(self, overview: dict) -> None:
        cpu_alert_percent = get_setting("cpu_alert_percent", self.settings.cpu_alert_percent)
        ram_alert_percent = get_setting("ram_alert_percent", self.settings.ram_alert_percent)
        disk_alert_percent = get_setting("disk_alert_percent", self.settings.disk_alert_percent)

        if overview["cpu_percent"] >= cpu_alert_percent:
            await self.notifier.send("cpu_high", f"VPS alert: CPU {overview['cpu_percent']}%", reply_markup=quick_actions_markup())
        if overview["memory"]["percent"] >= ram_alert_percent:
            await self.notifier.send("ram_high", f"VPS alert: RAM {overview['memory']['percent']}%", reply_markup=quick_actions_markup())
        if overview["disk"]["percent"] >= disk_alert_percent:
            await self.notifier.send("disk_high", f"VPS alert: disk {overview['disk']['percent']}%", reply_markup=quick_actions_markup())

    async def _check_containers(self) -> None:
        for container in self.docker.list_containers():
            status = str(container.get("status", "")).lower()
            health = str(container.get("health", "")).lower()
            name = container.get("name") or container.get("id")
            if "exited" in status or status in {"stopped", "dead"}:
                await self.notifier.send(
                    f"container_down:{name}",
                    f"Container down: {name} ({status})",
                    reply_markup=quick_actions_markup(),
                )
            if health == "unhealthy":
                await self.notifier.send(
                    f"container_unhealthy:{name}",
                    f"Container unhealthy: {name}",
                    reply_markup=quick_actions_markup(),
                )

    async def _check_security_events(self) -> None:
        inserted_events = []
        for event in read_auth_events(self.settings.auth_log_path_list):
            inserted = add_security_event(event)
            if inserted:
                inserted_events.append(event)

        if not self.security_bootstrapped:
            self.security_bootstrapped = True
            if inserted_events:
                logger.info("Bootstrapped %s historical SSH events without Telegram spam", len(inserted_events))
            return

        if inserted_events:
            await self._send_security_digest(inserted_events)

    async def _send_security_digest(self, events: list[dict[str, str]]) -> None:
        by_type = Counter(event["event_type"] for event in events)
        by_ip = Counter(event.get("ip") or "unknown" for event in events)
        top_ips = ", ".join(f"{ip} x{count}" for ip, count in by_ip.most_common(5))
        parts = [f"{event_type}: {count}" for event_type, count in by_type.items()]
        text = (
            f"SSH security alert: {len(events)} new event(s)\n"
            f"{', '.join(parts)}\n"
            f"Top IPs: {top_ips}"
        )
        await self.notifier.send("security_digest", text, reply_markup=quick_actions_markup())


def quick_actions_markup() -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "Security", "callback_data": "security"},
                {"text": "Status", "callback_data": "status"},
            ],
            [
                {"text": "Containers", "callback_data": "containers"},
                {"text": "Audit", "callback_data": "audit"},
            ],
        ]
    }
