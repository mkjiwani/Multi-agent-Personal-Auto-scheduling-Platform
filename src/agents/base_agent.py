"""Abstract base class for all agents."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime


class BaseAgent(ABC):
    """Base class that all agents must inherit from."""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"agent.{name}")
        self._running = False
        self._last_heartbeat: datetime | None = None
        self._last_run: datetime | None = None
        self._error: str | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def status(self) -> dict:
        return {
            "name": self.name,
            "running": self._running,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "error": self._error,
        }

    async def start(self):
        """Start the agent's main loop."""
        self._running = True
        self._error = None
        self.logger.info(f"Agent {self.name} starting")
        try:
            await self.run()
        except asyncio.CancelledError:
            self.logger.info(f"Agent {self.name} cancelled")
        except Exception as e:
            self._error = str(e)
            self.logger.error(f"Agent {self.name} error: {e}")
            raise
        finally:
            self._running = False

    async def stop(self):
        """Gracefully stop the agent."""
        self._running = False
        self.logger.info(f"Agent {self.name} stopping")

    def heartbeat(self):
        """Update heartbeat timestamp."""
        self._last_heartbeat = datetime.utcnow()

    @abstractmethod
    async def run(self):
        """Main agent loop. Must be implemented by subclasses."""
        ...

    @abstractmethod
    async def execute(self):
        """Execute the agent's core task once. Called by run() on schedule."""
        ...

    async def run_loop(self, interval_seconds: int = 3600, initial_delay: int = 0):
        """Standard run loop — execute periodically."""
        if initial_delay > 0:
            await asyncio.sleep(initial_delay)
        while self._running:
            self.heartbeat()
            try:
                await self.execute()
                self._last_run = datetime.utcnow()
                self._error = None
            except Exception as e:
                self._error = str(e)
                self.logger.error(f"Execution error: {e}")
            await asyncio.sleep(interval_seconds)
