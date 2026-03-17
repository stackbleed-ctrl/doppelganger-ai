# Architecture — Doppelganger v1.0.0

## Overview

Doppelganger is built around a central **async priority event bus**. All six layers communicate exclusively through pub/sub — no direct imports between layers at runtime. Any layer can be replaced, upgraded, or disabled without touching the others.

```
┌──────────────────────────────────────────────────────────┐
│                    Event Bus                             │
│    asyncio priority queue · wildcard subscriptions       │
└──┬──────────┬──────────┬──────────┬──────────┬──────────┘
   │          │          │          │          │
Perception  Memory   Reasoning   Agents    Voice+Interface
```

## Event Topology

| Publisher | Topic | Subscribers |
|---|---|---|
| Perception | `perception.*` | Memory, Proactive |
| Perception | `perception.presence_changed` | Reasoning, Proactive |
| Perception | `perception.stress_estimate` | Memory |
| Memory | `memory.updated` | Reasoning, Proactive |
| Reasoning | `reasoning.plan_ready` | Agents |
| Voice | `voice.transcript` | Agents, Personas |
| Voice | `voice.wake_word` | Voice (activates listen-once) |
| Voice | `voice.emotion_detected` | Memory |
| Agents | `agent.response` | Voice, Memory |
| Personas | `persona.switched` | Agents |
| Proactive | `proactive.suggestion` | Voice, Memory |
| Calendar | `calendar.synced` | Memory, Proactive |

## Layer Details

### Perception
Three sensing modalities — all gracefully degrade if hardware or deps are missing.

**WiFi CSI** — reads raw CSI from `/dev/csi0` (nexmon). Computes amplitude variance (movement), phase FFT (breathing rate 0.15–0.6 Hz), pose classification, gesture detection. Falls back to simulated data for development.

**Typing cadence** — pynput passive keyboard monitoring. IKI variance + WPM + error rate + burst analysis → composite stress score 0–1. StressLevel: CALM / FOCUSED / ELEVATED / HIGH.

**System metrics** — psutil CPU/mem/battery polled every 5s. Heuristic presence from CPU activity. Calendar integration polls every 15 minutes.

### Memory — Dual-write + Tiered

Every `store()` call writes to:
1. JSON node store (hot tier, fast reads)
2. Qdrant vector store (semantic search)
3. Graphiti Neo4j KG (entity + relationship tracking)

Tiers: Hot (0–24h, full fidelity) → Warm (1–7d, Grok summaries) → Cold (7d+, entities only).

Entity extraction: fast regex for people/tech/dates/projects + deep Grok NER with relationship detection.

Importers: Obsidian (markdown + wiki-links), Notion (API v3, recursive blocks), Browser (Chrome/Firefox/Safari SQLite, domain clustering).

### Reasoning — World Simulation

Grok generates N seed assumptions → each world steps forward independently via `asyncio.gather` → terminal detection on `OUTCOME:` / `SCORE:` → synthesis of top-K worlds → single recommendation. Used by agents (tool), proactive engine, and direct API.

### Agents

N async workers. Priority queue. Tool calling loop (up to 6 rounds). Context injection: memories + perception state + persona system prompt.

Built-in tools: `memory_search`, `memory_store`, `run_skill`, `get_time`, `system_info`, `web_search`, `world_sim`. Dynamic tools auto-registered from skill manifests.

### Voice

Wake word (openWakeWord → Whisper fallback → energy threshold) → one-shot listen → VAD utterance detection → transcribe (Whisper, language auto-detected) → emotion analysis → publish `voice.transcript`. TTS routes by language: Kokoro (en/ja/zh) → Piper (eu languages) → gTTS (fallback). Diarization via pyannote.audio with speaker naming.

### Interface

FastAPI: REST + SSE streaming + WebSocket event bridge. OpenAPI at `/docs`. All new v3–v1.0 routes in `v3_routes.py` and `registry_routes.py`. Tauri desktop manages Python process lifecycle + system tray. React Native mobile with mDNS discovery.

## Adding a New Layer

1. Create `src/doppelganger/your_layer/`
2. Implement `async start()`, `async stop()`, optional `async health() -> dict`
3. Add to `Orchestrator._layers` in `core/orchestrator_v3.py`
4. Wire events in `Orchestrator._wire_events()`
5. Add routes in `interfaces/`
