"""
Grok Client
Thin async wrapper around xAI's OpenAI-compatible API.
Handles streaming, retries, token counting, and structured output.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx
from pydantic import BaseModel

from ..core.config import GrokSettings, get_settings

logger = logging.getLogger(__name__)

RETRY_CODES = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5  # seconds


class Message(BaseModel):
    role: str   # system | user | assistant | tool
    content: str | list[dict]
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None


class CompletionChunk(BaseModel):
    text: str
    finish_reason: str | None = None
    tool_calls: list[dict] | None = None
    usage: dict | None = None


class GrokClient:
    """
    Async client for xAI Grok API.
    Supports: chat completions, streaming, tool/function calling,
              structured JSON output, embeddings (when available).
    """

    def __init__(self, settings: GrokSettings | None = None) -> None:
        self.cfg = settings or get_settings().grok
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.cfg.base_url,
                headers={
                    "Authorization": f"Bearer {self.cfg.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(120.0, connect=10.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ─── Core completion ──────────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[Message] | list[dict],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        tool_choice: str | dict = "auto",
        response_format: dict | None = None,
        stream: bool = False,
    ) -> str | AsyncIterator[CompletionChunk]:
        """
        Non-streaming: returns full text.
        Streaming (stream=True): returns async generator of CompletionChunk.
        """
        payload = {
            "model": model or self.cfg.model,
            "messages": [
                m.model_dump(exclude_none=True) if isinstance(m, Message) else m
                for m in messages
            ],
            "temperature": temperature if temperature is not None else self.cfg.temperature,
            "max_tokens": max_tokens or self.cfg.max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice
        if response_format:
            payload["response_format"] = response_format

        if stream:
            return self._stream_chat(payload)
        return await self._complete_chat(payload)

    async def _complete_chat(self, payload: dict) -> str:
        for attempt in range(MAX_RETRIES):
            try:
                client = await self._get_client()
                resp = await client.post("/chat/completions", json=payload)
                if resp.status_code in RETRY_CODES and attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_BACKOFF ** attempt)
                    continue
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"] or ""
            except httpx.HTTPStatusError as e:
                if e.response.status_code not in RETRY_CODES or attempt == MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(RETRY_BACKOFF ** attempt)
        return ""

    async def _stream_chat(self, payload: dict) -> AsyncIterator[CompletionChunk]:
        client = await self._get_client()
        async with client.stream("POST", "/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    return
                try:
                    data = json.loads(data_str)
                    choice = data["choices"][0]
                    delta = choice.get("delta", {})
                    yield CompletionChunk(
                        text=delta.get("content") or "",
                        finish_reason=choice.get("finish_reason"),
                        tool_calls=delta.get("tool_calls"),
                        usage=data.get("usage"),
                    )
                except (json.JSONDecodeError, KeyError):
                    continue

    # ─── Structured output ────────────────────────────────────────────────────

    async def chat_json(
        self,
        messages: list[Message] | list[dict],
        schema: type[BaseModel],
        **kwargs,
    ) -> BaseModel:
        """Force JSON output conforming to a Pydantic model."""
        system_hint = {
            "role": "system",
            "content": (
                f"Respond ONLY with valid JSON matching this schema:\n"
                f"{json.dumps(schema.model_json_schema(), indent=2)}\n"
                "No prose, no markdown fences."
            ),
        }
        all_messages = [system_hint, *(
            m.model_dump(exclude_none=True) if isinstance(m, Message) else m
            for m in messages
        )]
        raw = await self._complete_chat({
            "model": kwargs.get("model", self.cfg.model),
            "messages": all_messages,
            "temperature": kwargs.get("temperature", 0.2),
            "max_tokens": kwargs.get("max_tokens", self.cfg.max_tokens),
            "stream": False,
            "response_format": {"type": "json_object"},
        })
        # Strip accidental fences
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return schema.model_validate_json(clean)

    # ─── Tool calling ─────────────────────────────────────────────────────────

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        max_rounds: int = 6,
        tool_executor: Any = None,
    ) -> tuple[str, list[dict]]:
        """
        Agentic loop: call Grok, execute any tool calls, feed results back.
        Returns (final_text, full_message_history).
        """
        history = list(messages)

        for _ in range(max_rounds):
            client = await self._get_client()
            resp = await client.post("/chat/completions", json={
                "model": self.cfg.model,
                "messages": history,
                "tools": tools,
                "tool_choice": "auto",
                "max_tokens": self.cfg.max_tokens,
                "stream": False,
            })
            resp.raise_for_status()
            data = resp.json()
            message = data["choices"][0]["message"]
            history.append(message)

            if not message.get("tool_calls"):
                return message.get("content") or "", history

            # Execute tool calls
            for tc in message["tool_calls"]:
                tool_name = tc["function"]["name"]
                tool_args = json.loads(tc["function"]["arguments"])
                logger.debug("Calling tool %s(%s)", tool_name, tool_args)

                if tool_executor:
                    result = await tool_executor(tool_name, tool_args)
                else:
                    result = {"error": f"No executor for {tool_name}"}

                history.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result),
                })

        return "Max tool rounds reached.", history


# Module-level singleton
_client: GrokClient | None = None


def get_grok() -> GrokClient:
    global _client
    if _client is None:
        _client = GrokClient()
    return _client
