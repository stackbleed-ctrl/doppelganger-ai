"""
Agent Runtime
Manages agent instances, tool registry, and task execution.
Each "task" is a unit of work dispatched by the reasoning layer or voice input.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine

from ..core.event_bus import Event, EventBus, EventPriority
from ..core.config import Settings
from .grok_client import GrokClient, get_grok
from .tools import BUILTIN_TOOLS, ToolExecutor

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    DONE      = "done"
    FAILED    = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentTask:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt: str = ""
    context: dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    source: str = "unknown"  # 'voice' | 'reasoning' | 'api' | 'skill'


class AgentRuntime:
    """
    Manages the lifecycle of agent tasks.
    Pulls from a task queue, builds context from memory,
    calls Grok with the appropriate tool set, then publishes the result.
    """

    def __init__(self, bus: EventBus, settings: Settings) -> None:
        self.bus = bus
        self.settings = settings
        self.grok: GrokClient = get_grok()
        self.tool_executor = ToolExecutor()
        self._queue: asyncio.Queue[AgentTask] = asyncio.Queue(maxsize=256)
        self._tasks: dict[str, AgentTask] = {}
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._system_prompt = self._build_system_prompt()

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self) -> None:
        self._running = True
        n_workers = self.settings.reasoning.max_parallel_worlds  # reuse concurrency setting
        self._workers = [
            asyncio.create_task(self._worker(i), name=f"agent-worker-{i}")
            for i in range(n_workers)
        ]
        logger.info("AgentRuntime started with %d workers", n_workers)

    async def stop(self) -> None:
        self._running = False
        for w in self._workers:
            w.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        await self.grok.close()

    async def health(self) -> dict:
        return {
            "queue_depth": self._queue.qsize(),
            "active_tasks": sum(1 for t in self._tasks.values() if t.status == TaskStatus.RUNNING),
            "total_tasks": len(self._tasks),
        }

    # ─── Event handlers (called by Orchestrator wiring) ──────────────────────

    async def on_voice_command(self, event: Event) -> None:
        transcript: str = event.payload.get("text", "")
        if not transcript.strip():
            return
        task = AgentTask(
            prompt=transcript,
            context={"perception": event.payload},
            source="voice",
        )
        await self.submit(task)

    async def on_plan(self, event: Event) -> None:
        plan: dict = event.payload
        task = AgentTask(
            prompt=plan.get("instruction", ""),
            context=plan.get("context", {}),
            source="reasoning",
        )
        await self.submit(task)

    # ─── Public API ───────────────────────────────────────────────────────────

    async def submit(self, task: AgentTask) -> str:
        self._tasks[task.id] = task
        await self._queue.put(task)
        logger.debug("Task queued: %s — %s", task.id[:8], task.prompt[:60])
        return task.id

    def get_task(self, task_id: str) -> AgentTask | None:
        return self._tasks.get(task_id)

    # ─── Worker loop ──────────────────────────────────────────────────────────

    async def _worker(self, worker_id: int) -> None:
        while self._running:
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._run_task(task, worker_id)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Worker %d error: %s", worker_id, e)

    async def _run_task(self, task: AgentTask, worker_id: int) -> None:
        task.status = TaskStatus.RUNNING
        logger.info("[W%d] Running task %s: %s", worker_id, task.id[:8], task.prompt[:80])

        try:
            messages = self._build_messages(task)
            result, history = await self.grok.chat_with_tools(
                messages=messages,
                tools=BUILTIN_TOOLS + self.tool_executor.skill_tools(),
                tool_executor=self.tool_executor.execute,
            )

            task.result = result
            task.status = TaskStatus.DONE
            task.completed_at = datetime.utcnow()

            await self.bus.publish_simple(
                "agent.response",
                payload={
                    "task_id": task.id,
                    "text": result,
                    "source": task.source,
                    "context": task.context,
                },
                source="agent_runtime",
            )

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.completed_at = datetime.utcnow()
            logger.error("Task %s failed: %s", task.id[:8], e)

            await self.bus.publish_simple(
                "agent.error",
                payload={"task_id": task.id, "error": str(e)},
                source="agent_runtime",
                priority=EventPriority.HIGH,
            )

    # ─── Message construction ─────────────────────────────────────────────────

    def _build_messages(self, task: AgentTask) -> list[dict]:
        messages = [{"role": "system", "content": self._system_prompt}]

        # Inject memory context if available
        if memories := task.context.get("memories"):
            ctx = "\n".join(f"- {m}" for m in memories[:10])
            messages.append({
                "role": "system",
                "content": f"Relevant memories about this person:\n{ctx}",
            })

        # Inject perception state
        if perception := task.context.get("perception"):
            messages.append({
                "role": "system",
                "content": f"Current environment state: {perception}",
            })

        messages.append({"role": "user", "content": task.prompt})
        return messages

    def _build_system_prompt(self) -> str:
        return """\
You are Doppelganger — a private, local-first AI twin that lives entirely on the user's machine.

Your personality:
- Direct and efficient. No filler.
- Proactively helpful: anticipate what's needed next.
- Honest about uncertainty.
- Never preachy or sycophantic.

Your capabilities:
- Access to the user's temporal knowledge graph (what they've done, said, cared about)
- Ability to call skills (email, home automation, calendar, etc.)
- Awareness of the user's environment via sensors
- Parallel world simulation for "what if" analysis

Privacy contract: Everything stays local. You never send data anywhere without explicit permission.

Always respond in first person as the user's digital twin. Be concise.
"""
