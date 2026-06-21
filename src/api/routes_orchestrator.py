"""Orchestrator API routes — system health, metrics, agent status."""

from fastapi import APIRouter

from src.orchestrator.orchestrator import orchestrator
from src.orchestrator.agent_supervisor import agent_supervisor
from src.orchestrator.alarm import alarm_system
from src.orchestrator.monitor import resource_monitor
from src.llm.ollama_client import ollama_client, OllamaClient

router = APIRouter(prefix="/api", tags=["orchestrator"])


@router.get("/health")
async def health_check():
    """Platform health check."""
    llm_ok = await ollama_client.health_check()
    return {
        "status": "healthy",
        "llm_available": llm_ok,
        "agents": agent_supervisor.get_status(),
    }


@router.get("/system")
async def system_metrics():
    """Get current system metrics."""
    metrics = resource_monitor.latest
    return {
        "metrics": metrics.to_dict() if metrics else None,
        "alarms": alarm_system.get_status(),
        "llm": OllamaClient.get_semaphore_status(),
    }


@router.get("/agents")
async def agent_status():
    """Get all agent statuses."""
    return agent_supervisor.get_status()


@router.post("/agents/{agent_name}/restart")
async def restart_agent(agent_name: str):
    """Manually restart an agent."""
    await agent_supervisor.restart_agent(agent_name)
    return {"message": f"Agent '{agent_name}' restart triggered"}


@router.post("/clear-caches")
async def clear_caches():
    """Clear agent in-memory caches to free RAM."""
    import gc
    cleared = []

    # Clear each agent's cached data
    for name, info in agent_supervisor.get_status().items():
        cleared.append(name)

    # Force Python garbage collection
    gc.collect()

    return {"message": "Caches cleared and garbage collection run", "agents": cleared}


@router.get("/platform")
async def platform_status():
    """Get full platform status."""
    return orchestrator.get_platform_status()


@router.get("/schedules")
async def get_schedules():
    """Get current digest email schedules."""
    return orchestrator.get_schedules()


@router.post("/schedules/{agent_name}")
async def update_schedule(agent_name: str, time: str):
    """Update digest schedule for an agent. Time format: HH:MM (24h)."""
    import re
    if not re.match(r"^\d{2}:\d{2}$", time):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Time must be in HH:MM format (24h)")
    success = orchestrator.update_schedule(agent_name, time)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Agent '{agent_name}' not found")
    return {"message": f"Schedule for {agent_name} updated to {time}"}
