# Doppelganger Architecture

## Overview

Doppelganger is built around a central async event bus. All five layers communicate exclusively through pub/sub — no direct imports between layers at runtime.

```
┌─────────────────────────────────────────────────┐
│                   Event Bus                     │
│         (asyncio priority queue, wildcard       │
│          subscriptions, topic routing)          │
└──────┬──────────┬──────────┬──────────┬─────────┘
       │          │          │          │
  Perception  Memory    Reasoning   Agents    Voice
```

## Event topology

| Publisher | Topic | Subscribers |
|---|---|---|
| Perception | `perception.*` | Memory, Reasoning |
| Perception | `perception.presence_changed` | Reasoning |
| Memory | `memory.updated` | Reasoning |
| Reasoning | `reasoning.plan_ready` | Agents |
| Voice | `voice.transcript` | Agents |
| Agents | `agent.response` | Voice, Memory |
| Agents | `agent.error` | (logged) |

## Layer details

### Perception
- **WiFi CSI**: Reads raw 802.11 CSI from `/dev/csi0` (nexmon). Computes amplitude variance (movement), phase series (breathing). Falls back to simulated data for development.
- **Microphone**: pyaudio stream → VAD energy threshold → publishes `perception.mic_activity`
- **System metrics**: psutil CPU/mem/battery polled every N seconds → heuristic presence inference

### Memory
- **Short-term**: in-memory episodic buffer (last 128 events)
- **Vector store**: Qdrant for semantic search. Embeddings via local Ollama (nomic-embed-text) or falls back to keyword search
- **Knowledge graph**: JSON-persisted node/edge store with auto-inferred edges from tag overlap. Neo4j/Graphiti integration planned for v0.2
- **Consolidation**: hourly background task compresses episodic buffer

### Reasoning
- **World seeding**: Grok-3 generates N diverse initial assumptions for a scenario
- **Parallel simulation**: each world steps forward independently via `asyncio.gather`
- **Scoring**: utility score extracted from `SCORE: 0.0-1.0` terminal output
- **Synthesis**: top-K worlds merged into a single recommendation

### Agents
- **Worker pool**: N async workers pulling from a priority queue
- **Tool calling**: Grok function-calling loop with up to 6 rounds
- **Skills**: dynamically loaded from `skills/` at runtime via `importlib`

### Voice
- **STT**: faster-whisper with webrtcvad for utterance boundary detection
- **TTS**: Kokoro (preferred) or Piper. Runs in thread pool to avoid blocking event loop

### Interface
- **REST**: FastAPI with full OpenAPI docs at `/docs`
- **SSE**: `/chat/stream` for streaming chat responses
- **WebSocket**: `/ws` forwards relevant bus events to all connected clients
- **CLI**: Typer + Rich for terminal UX

## Adding a layer

1. Create `src/doppelganger/your_layer/`
2. Implement `async def start()`, `async def stop()`, optional `async def health() -> dict`
3. Register in `Orchestrator._layers`
4. Wire events in `Orchestrator._wire_cross_layer_events()`
