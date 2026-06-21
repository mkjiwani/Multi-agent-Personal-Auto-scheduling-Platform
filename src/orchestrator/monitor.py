"""System resource monitor — CPU, RAM, disk, threads. Updates every ≤5 seconds."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, asdict
from datetime import datetime

import psutil

logger = logging.getLogger(__name__)


@dataclass
class SystemMetrics:
    cpu_percent: float
    ram_percent: float
    disk_percent: float
    active_threads: int
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


class ResourceMonitor:
    """Monitors system resources and broadcasts updates."""

    def __init__(self, interval: float = 5.0):
        self.interval = interval
        self._running = False
        self._latest: SystemMetrics | None = None
        self._subscribers: list[asyncio.Queue] = []

    @property
    def latest(self) -> SystemMetrics | None:
        return self._latest

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to metric updates. Returns a queue that receives SystemMetrics."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=10)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        """Remove a subscriber."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def start(self):
        """Start the monitoring loop."""
        self._running = True
        logger.info("Resource monitor started (interval: %.1fs)", self.interval)
        while self._running:
            metrics = self._collect()
            self._latest = metrics
            await self._broadcast(metrics)
            await asyncio.sleep(self.interval)

    def stop(self):
        """Stop the monitoring loop."""
        self._running = False
        logger.info("Resource monitor stopped")

    def _collect(self) -> SystemMetrics:
        """Collect current system metrics."""
        return SystemMetrics(
            cpu_percent=psutil.cpu_percent(interval=None),
            ram_percent=psutil.virtual_memory().percent,
            disk_percent=psutil.disk_usage("/").percent,
            active_threads=psutil.Process().num_threads(),
            timestamp=datetime.utcnow().isoformat(),
        )

    async def _broadcast(self, metrics: SystemMetrics):
        """Send metrics to all subscribers."""
        dead_queues = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(metrics)
            except asyncio.QueueFull:
                # Drop oldest and put new
                try:
                    queue.get_nowait()
                    queue.put_nowait(metrics)
                except asyncio.QueueEmpty:
                    pass
            except Exception:
                dead_queues.append(queue)

        for q in dead_queues:
            self._subscribers.remove(q)


# Singleton
resource_monitor = ResourceMonitor()
