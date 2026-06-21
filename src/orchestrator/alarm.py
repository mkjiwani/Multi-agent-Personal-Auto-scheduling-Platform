"""Alarm system — triggers when resources exceed thresholds."""

import logging
from dataclasses import dataclass

from src.config import settings
from src.orchestrator.monitor import SystemMetrics

logger = logging.getLogger(__name__)


@dataclass
class Alarm:
    resource: str  # "cpu", "ram", "disk"
    current_value: float
    threshold: float
    suggestion: str
    active: bool = True


# Corrective action suggestions
SUGGESTIONS = {
    "cpu": [
        "Consider pausing non-critical agents to reduce CPU load",
        "Reduce LLM inference frequency or lower max_tokens",
        "Check for runaway processes with high CPU usage",
    ],
    "ram": [
        "Clear agent caches to free memory",
        "Restart agents with high memory footprint",
        "Reduce batch sizes for data processing",
    ],
    "disk": [
        "Clear old database entries and log files",
        "Remove cached data older than 7 days",
        "Check for large log files that can be rotated",
    ],
}


class AlarmSystem:
    """Checks system metrics against thresholds and generates alarms."""

    def __init__(self):
        self._active_alarms: dict[str, Alarm] = {}
        self._suggestion_index: dict[str, int] = {"cpu": 0, "ram": 0, "disk": 0}

    @property
    def active_alarms(self) -> list[Alarm]:
        return [a for a in self._active_alarms.values() if a.active]

    def check(self, metrics: SystemMetrics) -> list[Alarm]:
        """Check metrics against thresholds. Returns newly triggered alarms."""
        new_alarms = []

        checks = [
            ("cpu", metrics.cpu_percent, settings.alarm_cpu_threshold),
            ("ram", metrics.ram_percent, settings.alarm_ram_threshold),
            ("disk", metrics.disk_percent, settings.alarm_disk_threshold),
        ]

        for resource, value, threshold in checks:
            if value >= threshold:
                if resource not in self._active_alarms or not self._active_alarms[resource].active:
                    alarm = Alarm(
                        resource=resource,
                        current_value=value,
                        threshold=threshold,
                        suggestion=self._get_suggestion(resource),
                    )
                    self._active_alarms[resource] = alarm
                    new_alarms.append(alarm)
                    logger.warning(
                        f"ALARM: {resource.upper()} at {value:.1f}% (threshold: {threshold}%)"
                    )
                else:
                    # Update current value
                    self._active_alarms[resource].current_value = value
            else:
                # Clear alarm if value drops below threshold
                if resource in self._active_alarms and self._active_alarms[resource].active:
                    self._active_alarms[resource].active = False
                    logger.info(f"ALARM CLEARED: {resource.upper()} back to {value:.1f}%")

        return new_alarms

    def _get_suggestion(self, resource: str) -> str:
        """Get a rotating corrective action suggestion."""
        suggestions = SUGGESTIONS.get(resource, ["Monitor the situation"])
        idx = self._suggestion_index.get(resource, 0)
        suggestion = suggestions[idx % len(suggestions)]
        self._suggestion_index[resource] = idx + 1
        return suggestion

    def get_status(self) -> dict:
        """Get alarm system status for dashboard."""
        return {
            "active_alarms": [
                {
                    "resource": a.resource,
                    "current_value": a.current_value,
                    "threshold": a.threshold,
                    "suggestion": a.suggestion,
                }
                for a in self.active_alarms
            ],
            "all_clear": len(self.active_alarms) == 0,
        }


# Singleton
alarm_system = AlarmSystem()
