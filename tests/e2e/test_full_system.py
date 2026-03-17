"""
End-to-End Test Suite
Tests the complete Doppelganger system from API to storage.
Requires: running backend (or uses TestClient for in-process testing).

Run: pytest tests/e2e/ -v --timeout=60
"""

import asyncio
import json
import time
import pytest
import pytest_asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def app(tmp_path_factory):
    """Spin up a full in-process Doppelganger app for testing."""
    import os
    tmp = tmp_path_factory.mktemp("doppelganger_test")
    os.environ["XAI_API_KEY"] = "test_key_not_real"
    os.environ["DOPPELGANGER_DEBUG"] = "true"

    # Patch Grok to avoid real API calls
    with patch("doppelganger.agents.grok_client.GrokClient.chat", new_callable=AsyncMock) as mock_chat, \
         patch("doppelganger.agents.grok_client.GrokClient.chat_with_tools", new_callable=AsyncMock) as mock_tools:

        mock_chat.return_value = "Test response from Doppelganger"
        mock_tools.return_value = ("Test tool response", [])

        from doppelganger.core.config import Settings
        settings = Settings(data_dir=tmp)

        from doppelganger.interfaces.api import create_app
        fastapi_app = create_app()

        yield fastapi_app


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        # Wait for startup
        for _ in range(10):
            try:
                resp = await c.get("/health")
                if resp.status_code == 200:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.5)
        yield c


# ─── Health & boot ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "uptime_sec" in data
    assert "layers" in data


@pytest.mark.asyncio
async def test_health_includes_all_layers(client):
    resp = await client.get("/health")
    layers = resp.json().get("layers", {})
    expected = ["MemoryManager", "PerceptionPipeline", "ReasoningSwarm", "AgentRuntime"]
    for layer in expected:
        assert layer in layers, f"Missing layer: {layer}"


# ─── Chat API ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_basic(client):
    resp = await client.post("/chat", json={"message": "Hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert "task_id" in data
    assert len(data["response"]) > 0


@pytest.mark.asyncio
async def test_chat_empty_message(client):
    resp = await client.post("/chat", json={"message": ""})
    # Should return error or empty gracefully
    assert resp.status_code in (200, 400, 422)


@pytest.mark.asyncio
async def test_chat_long_message(client):
    long_msg = "test " * 500
    resp = await client.post("/chat", json={"message": long_msg})
    assert resp.status_code in (200, 422)


@pytest.mark.asyncio
async def test_chat_stream_sse(client):
    """Test SSE streaming endpoint returns valid event stream."""
    async with client.stream("POST", "/chat/stream", json={"message": "Hello", "stream": True}) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        chunks = []
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                data = json.loads(line[6:])
                chunks.append(data)
                if data.get("done"):
                    break
        assert len(chunks) > 0


# ─── Memory API ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_store_and_retrieve(client):
    content = f"E2E test memory {time.time()}"
    
    # Store
    resp = await client.post("/memory/store", json={"content": content, "tags": ["e2e_test"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["stored"] is True
    node_id = data["id"]
    assert len(node_id) > 0

    # Search
    await asyncio.sleep(0.2)  # let indexing happen
    resp = await client.post("/memory/search", json={"query": "E2E test memory", "limit": 5})
    assert resp.status_code == 200
    results = resp.json()["results"]
    # Should find our stored memory
    contents = [r["content"] for r in results]
    assert any("E2E test memory" in c for c in contents)


@pytest.mark.asyncio
async def test_memory_timeline(client):
    # Store something first
    await client.post("/memory/store", json={"content": "Timeline test event", "tags": ["timeline"]})
    await asyncio.sleep(0.1)

    resp = await client.get("/memory/timeline?hours=1")
    assert resp.status_code == 200
    nodes = resp.json()["nodes"]
    assert isinstance(nodes, list)


@pytest.mark.asyncio
async def test_memory_search_empty_query(client):
    resp = await client.post("/memory/search", json={"query": "", "limit": 5})
    assert resp.status_code in (200, 422)


@pytest.mark.asyncio
async def test_memory_search_with_tags(client):
    unique_tag = f"test_tag_{int(time.time())}"
    await client.post("/memory/store", json={"content": "Tagged memory", "tags": [unique_tag]})
    await asyncio.sleep(0.1)

    resp = await client.post("/memory/search", json={"query": "Tagged", "tags": [unique_tag], "limit": 5})
    assert resp.status_code == 200


# ─── Persona API ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_personas_list(client):
    resp = await client.get("/personas")
    assert resp.status_code == 200
    data = resp.json()
    assert "personas" in data
    assert "active_id" in data
    assert len(data["personas"]) >= 1


@pytest.mark.asyncio
async def test_persona_switch(client):
    resp = await client.post("/personas/work/activate")
    assert resp.status_code == 200
    data = resp.json()
    assert "switched_to" in data

    # Switch back
    await client.post("/personas/default/activate")


@pytest.mark.asyncio
async def test_persona_switch_invalid(client):
    resp = await client.post("/personas/nonexistent_persona/activate")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_persona_create_and_delete(client):
    # Create
    resp = await client.post("/personas", json={
        "id": "test_persona_e2e",
        "name": "Test E2E",
        "description": "Test persona",
        "system_prompt": "You are a test.",
    })
    assert resp.status_code == 200

    # Verify it appears in list
    resp = await client.get("/personas")
    names = [p["id"] for p in resp.json()["personas"]]
    assert "test_persona_e2e" in names

    # Delete
    resp = await client.delete("/personas/test_persona_e2e")
    assert resp.status_code == 200


# ─── Reasoning / Simulation API ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_simulation_basic(client):
    resp = await client.post("/reasoning/simulate", json={
        "scenario": "What if I take a 10-minute break?",
        "steps": 2,
        "n_worlds": 2,
    }, timeout=30.0)
    assert resp.status_code == 200
    data = resp.json()
    assert "best_action" in data
    assert "synthesis" in data
    assert "worlds" in data
    assert len(data["worlds"]) >= 1
    assert 0.0 <= data["confidence"] <= 1.0


# ─── Skills API ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_skills_list(client):
    resp = await client.get("/skills")
    assert resp.status_code == 200
    data = resp.json()
    assert "skills" in data
    assert isinstance(data["skills"], list)


@pytest.mark.asyncio
async def test_skill_run_minecraft(client):
    resp = await client.post("/skills/minecraft_assistant/run", json={
        "query": "What materials do I need to craft a sword?",
        "mode": "recipe",
    }, timeout=15.0)
    # Skill may not be present in test env — both 200 and 404 are valid
    assert resp.status_code in (200, 404)


# ─── Perception API ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_presence_endpoint(client):
    resp = await client.get("/perception/presence")
    assert resp.status_code == 200
    data = resp.json()
    assert "detected" in data
    assert "activity" in data
    assert "confidence" in data
    assert 0.0 <= data["confidence"] <= 1.0


# ─── Proactive API ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_proactive_suggestions_empty(client):
    resp = await client.get("/proactive/suggestions?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "suggestions" in data
    assert isinstance(data["suggestions"], list)


# ─── WebSocket ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_websocket_ping_pong(client):
    from httpx_ws import aconnect_ws
    try:
        async with aconnect_ws("/ws", client) as ws:
            await ws.send_json({"type": "ping"})
            msg = await asyncio.wait_for(ws.receive_json(), timeout=3.0)
            assert msg["type"] == "pong"
            assert "ts" in msg
    except ImportError:
        pytest.skip("httpx-ws not installed")


@pytest.mark.asyncio
async def test_websocket_chat_ack(client):
    from httpx_ws import aconnect_ws
    try:
        async with aconnect_ws("/ws", client) as ws:
            await ws.send_json({"type": "chat", "text": "Hello from test"})
            msg = await asyncio.wait_for(ws.receive_json(), timeout=5.0)
            assert msg["type"] == "chat_ack"
            assert "task_id" in msg
    except ImportError:
        pytest.skip("httpx-ws not installed")


# ─── Data integrity ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_persistence_across_requests(client):
    """Memories stored in one request should be retrievable in another."""
    unique = f"persistence_test_{time.time()}"
    
    await client.post("/memory/store", json={"content": unique, "tags": ["persistence"]})
    await asyncio.sleep(0.3)
    
    resp = await client.post("/memory/search", json={"query": unique.split("_")[0], "limit": 10})
    results = resp.json()["results"]
    assert any(unique in r["content"] for r in results), "Memory not persisted across requests"


@pytest.mark.asyncio  
async def test_concurrent_requests(client):
    """System should handle multiple concurrent requests without corruption."""
    tasks = [
        client.post("/memory/store", json={"content": f"concurrent test {i}", "tags": ["concurrent"]}),
        client.get("/health"),
        client.get("/personas"),
        client.post("/memory/search", json={"query": "concurrent", "limit": 3}),
    ]
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    for r in responses:
        if not isinstance(r, Exception):
            assert r.status_code in (200, 201)
