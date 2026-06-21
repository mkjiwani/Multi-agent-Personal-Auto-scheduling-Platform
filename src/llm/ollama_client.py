"""Async Ollama client wrapper for Qwen3. Respects LLM semaphore."""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Global semaphore: only one agent can use the LLM at a time
llm_semaphore = asyncio.Semaphore(1)

# Track which agent currently holds the semaphore
_current_holder: str | None = None
_waiting_queue: list[str] = []


class OllamaClient:
    """Async client for Ollama API (OpenAI-compatible)."""

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model
        self.timeout = httpx.Timeout(300.0, connect=10.0)

    async def generate(
        self,
        prompt: str,
        agent_name: str = "unknown",
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        think: bool = True,
    ) -> str:
        """Generate a response from the LLM. Acquires semaphore first."""
        global _current_holder

        _waiting_queue.append(agent_name)
        logger.info(f"[LLM] {agent_name} waiting for semaphore (queue: {_waiting_queue})")

        try:
            async with asyncio.timeout(300):  # 5 min max wait
                await llm_semaphore.acquire()
        except asyncio.TimeoutError:
            _waiting_queue.remove(agent_name)
            logger.error(f"[LLM] {agent_name} timed out waiting for semaphore")
            raise TimeoutError(f"Agent '{agent_name}' timed out waiting for LLM access")

        _waiting_queue.remove(agent_name)
        _current_holder = agent_name
        logger.info(f"[LLM] {agent_name} acquired semaphore")

        try:
            return await self._call_ollama(prompt, system_prompt, temperature, max_tokens, think)
        finally:
            _current_holder = None
            llm_semaphore.release()
            logger.info(f"[LLM] {agent_name} released semaphore")
            # Yield to event loop so other waiting agents can acquire
            await asyncio.sleep(0)

    async def _call_ollama(
        self,
        prompt: str,
        system_prompt: str | None,
        temperature: float,
        max_tokens: int | None,
        think: bool = True,
    ) -> str:
        """Make the actual HTTP call to Ollama."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # For Qwen3: disable thinking mode for fast, short responses
        if not think:
            prompt = prompt.rstrip() + " /no_think"

        messages.append({"role": "user", "content": prompt})

        options = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": options,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            content = data["message"]["content"]
            # Strip Qwen3 <think>...</think> reasoning blocks
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
            return content

    async def health_check(self) -> bool:
        """Check if Ollama is reachable and the model is available."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    available = any(
                        self.model in m.get("name", "") for m in models
                    )
                    return available
        except Exception:
            return False
        return False

    @staticmethod
    def get_semaphore_status() -> dict:
        """Get current LLM semaphore status for monitoring."""
        return {
            "current_holder": _current_holder,
            "waiting_queue": list(_waiting_queue),
            "is_locked": llm_semaphore.locked(),
        }


# Singleton instance
ollama_client = OllamaClient()
