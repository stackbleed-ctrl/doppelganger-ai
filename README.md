<div align="center">

<img src="https://raw.githubusercontent.com/doppelganger-ai/doppelganger/main/docs/banner.png" alt="Doppelganger AI" width="800" />

# 🧬 Doppelganger AI

**Your private, local-first AI twin.**
Perceives your environment. Remembers everything. Reasons in parallel worlds. Speaks back.
100% local. No cloud. No telemetry. No subscriptions.

[![CI](https://github.com/doppelganger-ai/doppelganger/actions/workflows/ci.yml/badge.svg)](https://github.com/doppelganger-ai/doppelganger/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker/docker-compose.yml)
[![Discord](https://img.shields.io/badge/discord-join-7289da.svg)](https://discord.gg/doppelganger)

</div>

---

## ⚡ One command. Your twin is alive.

```bash
git clone https://github.com/doppelganger-ai/doppelganger
cd doppelganger
cp .env.example .env          # add your XAI_API_KEY
docker compose up
```

Open `http://localhost:3000`. Talk to your twin.

---

## What is this?

Doppelganger is an AI that runs **entirely on your machine** and learns to be *you*.

It senses your environment via WiFi CSI (presence detection without cameras), microphone, and system telemetry. It builds a persistent, temporal knowledge graph of your life. It simulates parallel "what if" worlds to help you make decisions. It speaks back with a natural voice. And it does all of this privately — nothing leaves your machine.

```
Perception → Memory → Reasoning Swarm → Action Engine → Voice / Web
          ↑                  ↓
       Feedback loop (learns from your reactions)
```

---

## 🏗️ Architecture

| Layer | Tech | What it does |
|---|---|---|
| **Perception** | WiFi CSI (nexmon) · pyaudio · psutil | Senses your presence, activity, stress |
| **Memory** | Graphiti · Qdrant · Neo4j | Temporal knowledge graph — never forgets |
| **Reasoning** | LangGraph Swarm · Grok-3 | Parallel world simulation for decisions |
| **Action** | Skills marketplace | Sandboxed plugin execution |
| **Voice** | faster-whisper · Kokoro TTS | Real-time STT + natural speech synthesis |
| **Interface** | FastAPI · React/Vite · WebSocket | Web dashboard + REST API + CLI |

---

## 🎯 5 things Doppelganger does that nothing else does

**1. Presence without cameras**
WiFi Channel State Information (CSI) detects if you're in the room, estimates your activity (typing, walking, idle), and infers your breathing rate — all without any camera or wearable.

**2. Temporal memory graph**
Every interaction, every event, every preference is stored in a local knowledge graph with time-aware relationships. Ask "what was I working on last Tuesday?" and get a real answer.

**3. Parallel world simulation**
Type "what if I quit my job?" and Doppelganger spins up 4 parallel world simulations simultaneously, scores each outcome by utility, and synthesizes a recommendation.

**4. Skills marketplace**
Add any capability by dropping a folder into `skills/`. Two files: `manifest.json` + `skill.py`. The agent discovers it automatically and can call it via function calling.

**5. Voice-first, on your hardware**
`faster-whisper` transcribes locally at near-realtime speed. `Kokoro` synthesizes natural speech. No Whisper API, no ElevenLabs, no subscriptions.

---

## 🎛️ Docker Compose services

```yaml
core:      FastAPI orchestrator + agent runtime
sensing:   WiFi CSI sensor (optional, --profile wifi-csi)
qdrant:    Vector store (semantic memory search)
neo4j:     Knowledge graph (relationship tracking)
ollama:    Local embeddings (optional, --profile ollama)
frontend:  React dashboard
```

### Enable WiFi CSI sensing

```bash
docker compose --profile wifi-csi up
```

Requires a compatible Broadcom NIC with [nexmon_csi](https://github.com/seemoo-lab/nexmon_csi) or the [Linux CSI Tool](https://linux80211.parsec.kr). Falls back to CPU + mic heuristics automatically if hardware is unavailable.

---

## 🔌 Skills Marketplace

The fastest way to extend Doppelganger. Add any skill as a folder:

```
skills/
└── my_skill/
    ├── manifest.json    ← parameter schema + metadata
    └── skill.py         ← async def run(params) -> dict
```

**Built-in skills:**

| Skill | What it does |
|---|---|
| `email_autoreply` | Reads IMAP inbox, drafts context-aware replies in your style |
| `smart_home` | Controls Home Assistant devices (lights, thermostat, etc.) |
| `minecraft_assistant` | Crafting recipes, mob strategies, build planning |

**Adding a skill takes 5 minutes.** See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## 🖥️ CLI

```bash
# Start the daemon
doppelganger start

# Chat (streaming)
doppelganger chat "What should I focus on today?"

# Search memory
doppelganger memory search "project ideas from last week"

# Timeline
doppelganger memory timeline --hours 48

# Store a memory
doppelganger memory store "I decided to learn Rust this month"

# Simulate a scenario
doppelganger simulate "What if I move to Tokyo?" --worlds 4

# List installed skills
doppelganger skills
```

---

## 🔑 Configuration

Copy `.env.example` to `.env` and set your keys:

```bash
# Required
XAI_API_KEY=your_key_here

# Optional — enable WiFi CSI
ENABLE_WIFI_CSI=true

# Optional — email skill
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_ADDRESS=you@gmail.com
EMAIL_PASSWORD=app_password

# Optional — Home Assistant
HOME_ASSISTANT_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=your_token
```

All settings can be overridden in `config/user.yaml` or via `DOPPELGANGER__` prefixed environment variables.

---

## 🔒 Privacy

- **Everything local**: all inference runs on your hardware
- **No telemetry**: zero data leaves your machine
- **No accounts**: no cloud sync, no analytics
- **Open source**: read every line

---

## 🛣️ Roadmap

- [ ] Tauri desktop app (native, no Docker needed)
- [ ] iOS/Android companion (local WiFi only)
- [ ] Graphiti full temporal KG integration
- [ ] Persona switching (work vs personal)
- [ ] Proactive suggestions without prompting
- [ ] Plugin SDK + marketplace registry
- [ ] Multi-user household mode

---

## Contributing

Drop a skill, fix a bug, improve the docs. See [CONTRIBUTING.md](CONTRIBUTING.md).

The skills marketplace is how this project grows. **Every contributor who ships a skill becomes a maintainer.**

---

<div align="center">

Built with [Grok](https://x.ai) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [Kokoro](https://github.com/hexgrad/kokoro) · [Qdrant](https://qdrant.tech) · [LangGraph](https://langchain.com/langgraph)

**MIT License** — do whatever you want with it.

</div>
