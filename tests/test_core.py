"""
Doppelganger Test Suite
Unit tests — no external services required.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─── Event bus ───────────────────────────────────────────────────────────────

@pytest.fixture
async def bus():
    from doppelganger.core.event_bus import EventBus
    b = EventBus()
    await b.start()
    yield b
    await b.stop()


@pytest.mark.asyncio
async def test_event_bus_pubsub(bus):
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe("test.topic", handler)
    await bus.publish_simple("test.topic", {"value": 42}, source="test")
    await asyncio.sleep(0.1)

    assert len(received) == 1
    assert received[0].payload["value"] == 42


@pytest.mark.asyncio
async def test_event_bus_wildcard(bus):
    received = []

    async def handler(event):
        received.append(event.topic)

    bus.subscribe("perception.*", handler)
    await bus.publish_simple("perception.csi_frame", {}, source="test")
    await bus.publish_simple("perception.presence_changed", {}, source="test")
    await bus.publish_simple("voice.transcript", {}, source="test")  # should NOT match
    await asyncio.sleep(0.15)

    assert "perception.csi_frame" in received
    assert "perception.presence_changed" in received
    assert "voice.transcript" not in received


@pytest.mark.asyncio
async def test_event_bus_priority(bus):
    order = []

    async def handler(event):
        order.append(event.payload["n"])

    bus.subscribe("test.*", handler)

    from doppelganger.core.event_bus import Event, EventPriority
    # Publish low priority first, then critical
    await bus.publish(Event("test.low", {"n": 2}, priority=EventPriority.LOW))
    await bus.publish(Event("test.critical", {"n": 1}, priority=EventPriority.CRITICAL))
    await asyncio.sleep(0.15)

    assert order[0] == 1  # critical processed first


# ─── Config ──────────────────────────────────────────────────────────────────

def test_settings_defaults():
    from doppelganger.core.config import Settings
    s = Settings()
    assert s.version == "0.1.0"
    assert s.grok.model == "grok-3-latest"
    assert s.voice.stt_model == "base"


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("XAI_API_KEY", "test_key_123")
    monkeypatch.setenv("DOPPELGANGER_VOICE__STT_MODEL", "large-v3")
    from doppelganger.core.config import Settings
    s = Settings()
    assert s.grok.api_key == "test_key_123"
    assert s.voice.stt_model == "large-v3"


# ─── Memory ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def memory(tmp_path):
    from doppelganger.core.event_bus import EventBus
    from doppelganger.core.config import Settings
    from doppelganger.memory.memory_manager import MemoryManager

    bus = EventBus()
    await bus.start()
    s = Settings(data_dir=tmp_path)
    mm = MemoryManager(bus, s)
    await mm.start()
    yield mm
    await mm.stop()
    await bus.stop()


@pytest.mark.asyncio
async def test_memory_store_and_search(memory):
    node = await memory.store("I love building AI systems", tags=["work", "ai"])
    assert node.id
    assert node.content == "I love building AI systems"

    results = await memory.search("AI systems")
    assert len(results) > 0
    assert any("AI" in r["content"] for r in results)


@pytest.mark.asyncio
async def test_memory_timeline(memory):
    await memory.store("event one", tags=["test"])
    await memory.store("event two", tags=["test"])

    nodes = await memory.get_timeline(hours=1)
    assert len(nodes) >= 2


@pytest.mark.asyncio
async def test_memory_persistence(tmp_path):
    from doppelganger.core.event_bus import EventBus
    from doppelganger.core.config import Settings
    from doppelganger.memory.memory_manager import MemoryManager

    # Store something
    bus = EventBus()
    await bus.start()
    s = Settings(data_dir=tmp_path)
    mm = MemoryManager(bus, s)
    await mm.start()
    await mm.store("persistent memory", tags=["persist"])
    node_id = list(mm._nodes.keys())[0]
    await mm.stop()
    await bus.stop()

    # Reload and verify
    bus2 = EventBus()
    await bus2.start()
    mm2 = MemoryManager(bus2, s)
    await mm2.start()
    assert node_id in mm2._nodes
    await mm2.stop()
    await bus2.stop()


# ─── Skill loader ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_skill_loader_scans(tmp_path):
    import json
    from doppelganger.actions.skill_loader import SkillLoader

    # Create a minimal skill
    skill_dir = tmp_path / "test_skill"
    skill_dir.mkdir()
    (skill_dir / "manifest.json").write_text(json.dumps({
        "name": "test_skill",
        "version": "1.0.0",
        "description": "Test skill",
        "parameters": {"type": "object", "properties": {}},
    }))
    (skill_dir / "skill.py").write_text(
        "async def run(params):\n    return {'ok': True, 'params': params}\n"
    )

    loader = SkillLoader(skills_dir=tmp_path)
    skills = loader.list_skills()
    assert len(skills) == 1
    assert skills[0]["name"] == "test_skill"


@pytest.mark.asyncio
async def test_skill_execution(tmp_path):
    import json
    from doppelganger.actions.skill_loader import SkillLoader

    skill_dir = tmp_path / "echo_skill"
    skill_dir.mkdir()
    (skill_dir / "manifest.json").write_text(json.dumps({
        "name": "echo_skill",
        "version": "1.0.0",
        "description": "Echoes input",
        "parameters": {"type": "object", "properties": {"msg": {"type": "string"}}},
    }))
    (skill_dir / "skill.py").write_text(
        "async def run(params):\n    return {'echo': params.get('msg', '')}\n"
    )

    loader = SkillLoader(skills_dir=tmp_path)
    result = await loader.run("echo_skill", {"msg": "hello world"})
    assert result["echo"] == "hello world"


# ─── WiFi CSI ────────────────────────────────────────────────────────────────

def test_csi_simulation():
    from doppelganger.perception.wifi_csi import WiFiCSISensor
    # Always uses simulated frames since /dev/csi0 won't exist in CI
    sensor = WiFiCSISensor()
    frame = sensor._simulate_frame()
    assert frame.amplitude is not None
    assert frame.phase is not None

    state = sensor.infer_presence(frame)
    # Need 5 frames for inference
    for _ in range(5):
        frame = sensor._simulate_frame()
        state = sensor.infer_presence(frame)

    assert "confidence" in state
    assert "activity" in state
    assert 0.0 <= state["confidence"] <= 1.0
