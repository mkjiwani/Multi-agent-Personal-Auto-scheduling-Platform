"""Agent supervisor — launches agents as subprocesses, monitors health, auto-restarts."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    CRASHED = "crashed"
    RESTARTING = "restarting"


@dataclass
class AgentInfo:
    name: str
    module_path: str  # e.g., "src.agents.ai_times"
    status: AgentStatus = AgentStatus.STOPPED
    process: asyncio.subprocess.Process | None = None
    pid: int | None = None
    restart_count: int = 0
    max_restarts: int = 3
    last_heartbeat: datetime | None = None
    started_at: datetime | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "pid": self.pid,
            "restart_count": self.restart_count,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "error_message": self.error_message,
        }


class AgentSupervisor:
    """Manages agent lifecycle — start, stop, monitor, restart on crash."""

    def __init__(self):
        self._agents: dict[str, AgentInfo] = {}
        self._monitor_task: asyncio.Task | None = None
        self._output_tasks: dict[str, list[asyncio.Task]] = {}
        self._running = False

    @property
    def agents(self) -> dict[str, AgentInfo]:
        return self._agents

    def register(self, name: str, module_path: str):
        """Register an agent to be managed."""
        self._agents[name] = AgentInfo(name=name, module_path=module_path)
        logger.info(f"Agent registered: {name} ({module_path})")

    async def start_all(self):
        """Start all registered agents and begin monitoring."""
        self._running = True
        for name in self._agents:
            await self.start_agent(name)
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Agent supervisor started — monitoring all agents")

    async def stop_all(self):
        """Gracefully stop all agents."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
        for name in list(self._agents.keys()):
            await self.stop_agent(name)
        logger.info("All agents stopped")

    async def start_agent(self, name: str):
        """Start a single agent as a subprocess."""
        agent = self._agents.get(name)
        if not agent:
            logger.error(f"Agent not found: {name}")
            return

        agent.status = AgentStatus.STARTING
        agent.error_message = None

        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-m", agent.module_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            agent.process = process
            agent.pid = process.pid
            agent.status = AgentStatus.RUNNING
            agent.started_at = datetime.utcnow()
            agent.last_heartbeat = datetime.utcnow()
            logger.info(f"Agent started: {name} (PID: {process.pid})")

            # Stream subprocess output to main logger
            self._output_tasks[name] = [
                asyncio.create_task(self._stream_output(name, process.stdout, "stdout")),
                asyncio.create_task(self._stream_output(name, process.stderr, "stderr")),
            ]
        except Exception as e:
            agent.status = AgentStatus.CRASHED
            agent.error_message = str(e)
            logger.error(f"Failed to start agent {name}: {e}")

    async def _stream_output(self, name: str, stream, stream_type: str):
        """Read subprocess output line-by-line and relay to main logger."""
        agent_logger = logging.getLogger(f"src.agents.{name}")
        try:
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if not text:
                    continue
                # Parse log level from line if present, otherwise use INFO
                if "[ERROR]" in text or "ERROR:" in text:
                    agent_logger.error(text)
                elif "[WARNING]" in text or "WARNING:" in text:
                    agent_logger.warning(text)
                else:
                    agent_logger.info(text)
        except (asyncio.CancelledError, Exception):
            pass

    async def stop_agent(self, name: str):
        """Stop a single agent gracefully."""
        agent = self._agents.get(name)
        if not agent or not agent.process:
            return

        # Cancel output streaming tasks
        for task in self._output_tasks.pop(name, []):
            task.cancel()

        try:
            agent.process.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(agent.process.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                agent.process.kill()
                await agent.process.wait()
        except ProcessLookupError:
            pass

        agent.status = AgentStatus.STOPPED
        agent.process = None
        agent.pid = None
        logger.info(f"Agent stopped: {name}")

    async def restart_agent(self, name: str):
        """Restart a crashed agent."""
        agent = self._agents.get(name)
        if not agent:
            return

        if agent.restart_count >= agent.max_restarts:
            logger.error(f"Agent {name} exceeded max restarts ({agent.max_restarts})")
            agent.status = AgentStatus.CRASHED
            agent.error_message = "Max restarts exceeded"
            return

        agent.status = AgentStatus.RESTARTING
        agent.restart_count += 1
        logger.warning(f"Restarting agent {name} (attempt {agent.restart_count})")

        await self.stop_agent(name)
        await asyncio.sleep(5 * agent.restart_count)  # Exponential backoff: 5s, 10s, 15s
        await self.start_agent(name)

    async def _monitor_loop(self):
        """Monitor agent processes and restart crashed ones."""
        while self._running:
            for name, agent in self._agents.items():
                if agent.status == AgentStatus.RUNNING and agent.process:
                    if agent.process.returncode is not None:
                        # Process has exited
                        exit_code = agent.process.returncode
                        stderr = ""
                        if agent.process.stderr:
                            try:
                                stderr_bytes = await agent.process.stderr.read()
                                stderr = stderr_bytes.decode()[-500:]  # Last 500 chars
                            except Exception:
                                pass
                        agent.status = AgentStatus.CRASHED
                        agent.error_message = f"Exit code: {exit_code}. {stderr}"
                        logger.error(f"Agent {name} crashed (exit: {exit_code})")
                        await self.restart_agent(name)

            await asyncio.sleep(10)  # Check every 10 seconds

    def get_status(self) -> dict:
        """Get status of all agents for dashboard."""
        return {
            name: agent.to_dict()
            for name, agent in self._agents.items()
        }


# Singleton
agent_supervisor = AgentSupervisor()
