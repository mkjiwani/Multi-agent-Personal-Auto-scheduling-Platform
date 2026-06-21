"""Main orchestrator — ties together monitor, alarm, supervisor, and scheduling."""

from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import settings
from src.orchestrator.monitor import resource_monitor
from src.orchestrator.alarm import alarm_system
from src.orchestrator.agent_supervisor import agent_supervisor

logger = logging.getLogger(__name__)


class Orchestrator:
    """Central orchestrator managing all platform components."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._monitor_task: asyncio.Task | None = None
        self._alarm_task: asyncio.Task | None = None
        self._running = False

    async def startup(self):
        """Initialize and start all platform components."""
        logger.info("=== Orchestrator starting up ===")
        self._running = True

        # Register agents
        agent_supervisor.register("ai_times", "src.agents.ai_times")
        agent_supervisor.register("mailman", "src.agents.mailman")
        agent_supervisor.register("wallstreet_wolf", "src.agents.wallstreet_wolf")
        agent_supervisor.register("news_briefer", "src.agents.news_briefer")
        agent_supervisor.register("docvault", "src.agents.docvault")

        # Start resource monitor
        self._monitor_task = asyncio.create_task(resource_monitor.start())

        # Start alarm checking loop
        self._alarm_task = asyncio.create_task(self._alarm_loop())

        # Start agent supervisor
        await agent_supervisor.start_all()

        # Start scheduler for periodic tasks
        self._schedule_digests()
        self.scheduler.start()

        logger.info("=== Orchestrator fully operational ===")

    def _schedule_digests(self):
        """Schedule daily HTML digest emails based on config times."""
        from src.agents.ai_times import ai_times_agent
        from src.agents.mailman import mailman_agent
        from src.agents.wallstreet_wolf import wallstreet_wolf_agent
        from src.agents.news_briefer import news_briefer_agent

        schedules = [
            ("ai_times_digest", settings.schedule_ai_times, ai_times_agent.send_digest),
            ("mailman_summary", settings.schedule_mailman, mailman_agent.send_daily_summary),
            ("wallstreet_brief", settings.schedule_wallstreet, wallstreet_wolf_agent.send_daily_brief),
            ("news_digest", settings.schedule_news, news_briefer_agent.send_digest),
        ]

        for job_id, time_str, func in schedules:
            try:
                hour, minute = time_str.split(":")
                self.scheduler.add_job(
                    func,
                    trigger=CronTrigger(hour=int(hour), minute=int(minute)),
                    id=job_id,
                    replace_existing=True,
                    misfire_grace_time=3600,
                )
                logger.info(f"Scheduled {job_id} at {time_str}")
            except Exception as e:
                logger.error(f"Failed to schedule {job_id}: {e}")

    def update_schedule(self, agent: str, time_str: str) -> bool:
        """Update the schedule for a specific agent's digest."""
        job_map = {
            "ai_times": "ai_times_digest",
            "mailman": "mailman_summary",
            "wallstreet": "wallstreet_brief",
            "news": "news_digest",
        }
        job_id = job_map.get(agent)
        if not job_id:
            return False

        try:
            hour, minute = time_str.split(":")
            job = self.scheduler.get_job(job_id)
            if job:
                job.reschedule(CronTrigger(hour=int(hour), minute=int(minute)))
                logger.info(f"Rescheduled {job_id} to {time_str}")
                return True
        except Exception as e:
            logger.error(f"Failed to reschedule {job_id}: {e}")
        return False

    def get_schedules(self) -> dict:
        """Get current digest schedules."""
        return {
            "ai_times": settings.schedule_ai_times,
            "mailman": settings.schedule_mailman,
            "wallstreet": settings.schedule_wallstreet,
            "news": settings.schedule_news,
        }

    async def shutdown(self):
        """Gracefully shut down all components."""
        logger.info("=== Orchestrator shutting down ===")
        self._running = False

        # Stop scheduler
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

        # Stop agents
        await agent_supervisor.stop_all()

        # Stop monitor
        resource_monitor.stop()
        if self._monitor_task:
            self._monitor_task.cancel()

        # Stop alarm loop
        if self._alarm_task:
            self._alarm_task.cancel()

        logger.info("=== Orchestrator shutdown complete ===")

    async def _alarm_loop(self):
        """Continuously check metrics against alarm thresholds."""
        metrics_queue = resource_monitor.subscribe()
        try:
            while self._running:
                try:
                    metrics = await asyncio.wait_for(metrics_queue.get(), timeout=10.0)
                    alarm_system.check(metrics)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            resource_monitor.unsubscribe(metrics_queue)

    def get_platform_status(self) -> dict:
        """Get full platform status for dashboard."""
        return {
            "orchestrator": "running" if self._running else "stopped",
            "agents": agent_supervisor.get_status(),
            "system": resource_monitor.latest.to_dict() if resource_monitor.latest else None,
            "alarms": alarm_system.get_status(),
        }


# Singleton
orchestrator = Orchestrator()
