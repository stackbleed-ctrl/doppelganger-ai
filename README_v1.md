<div align="center">

# 🧬 Doppelganger AI

**Your private, local-first AI twin.**

It senses your presence through WiFi signals. Remembers everything in a temporal knowledge graph. Simulates parallel futures when you face decisions. Switches personas between work, personal, and focus modes. Surfaces insights before you ask. Speaks back in real time. Runs on your phone over LAN.

**Zero cloud. Zero subscriptions. Zero telemetry. Completely yours.**

[![CI](https://github.com/stackbleed-ctrl/doppelganger-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/stackbleed-ctrl/doppelganger-ai/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![Version](https://img.shields.io/badge/version-1.0.0-cyan.svg)](https://github.com/stackbleed-ctrl/doppelganger-ai/releases)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](docker/docker-compose.yml)

</div>

---

## ⚡ One command. Your twin is alive.

```bash
git clone https://github.com/stackbleed-ctrl/doppelganger-ai
cd doppelganger-ai
cp .env.example .env
# Add your XAI_API_KEY to .env
docker compose up
```

Open `http://localhost:3000` — your twin is ready.

---

## What is Doppelganger?

Doppelganger is a complete AI system that runs **100% on your own hardware**. No API calls for your personal data. No cloud sync. No accounts. Every thought, memory, and interaction stays on your machine — forever.

It is not a chatbot wrapper. It is a full perception → memory → reasoning → action stack that monitors your environment, learns your patterns, and acts proactively — like a real twin would.

```
Perception → Memory → Reasoning Swarm → Action Engine → Voice / Web / Mobile
          ↑                  ↓
       Feedback loop (learns from every interaction)
```

---

## 🏗️ Architecture — 6 Layers

| Layer | Technology | What it does |
|---|---|---|
| **Perception** | WiFi CSI · pyaudio · pynput · psutil | Senses presence, pose, breathing rate, typing stress, activity |
| **Memory** | Graphiti · Neo4j · Qdrant · compression tiers | Temporal knowledge graph — bi-temporal, entity-linked, never forgets |
| **Reasoning** | LangGraph Swarm · Grok-3 | Spins up N parallel worlds to simulate any scenario |
| **Action** | Plugin SDK · skills marketplace · sandboxed executor | 2 files to add any capability — email, home automation, anything |
| **Voice** | faster-whisper · Kokoro · wake word · diarization · emotion | Full voice I/O — 99 languages, multi-speaker, emotion-aware |
| **Interface** | FastAPI · React/Vite · WebSocket · Tauri desktop · React Native | Web · native desktop · iOS/Android — all local |

---

## 🌟 10 Things Doppelganger Does That Nothing Else Does

**1. WiFi presence detection — no cameras**
Channel State Information (CSI) detects your presence, estimates your activity (typing, walking, idle), measures your breathing rate, and infers body pose — all from WiFi signals. No camera. No wearable. No privacy trade-off.

**2. Temporal knowledge graph**
Every interaction, preference, and event is stored in a Neo4j-backed knowledge graph with bi-temporal versioning. Entities are automatically extracted and linked. Ask "what was I working on last Tuesday?" and get a real answer.

**3. Parallel world simulation**
Ask "what if I quit my job?" and Doppelganger simultaneously runs 4 parallel world simulations, scores each by utility, and synthesizes a recommendation. This is genuine multi-branch reasoning — not summarization.

**4. Persona system with auto-switching**
Four built-in personas: Default, Work (analytical, brief), Personal (warm, casual), Focus (minimal, zero filler). Doppelganger auto-detects context and switches automatically. Each persona has its own voice, temperature, and memory scope.

**5. Proactive engine — no prompting needed**
Morning briefs when you first appear. Evening summaries. Weekly reviews on Monday. Pattern insights from your behavior. Goal nudges mid-afternoon. Task reminders near deadlines. All generated without you asking.

**6. Voice emotion detection**
Analyzes pitch, energy, speech rate, and prosodic patterns to detect: neutral, happy, sad, angry, anxious, excited, tired. Stores significant emotional states in memory. Adapts responses to your current state.

**7. Typing cadence stress estimation**
Monitors inter-keystroke intervals, WPM, error rate, and burst patterns to estimate cognitive load. High stress triggers memory storage and can adjust persona behavior. Keystrokes never leave your machine.

**8. Memory compression with importance scoring**
Uses a forgetting curve model: recent memories stay full-fidelity, older ones compress into semantic summaries via Grok. Each node has an importance score based on recency, access frequency, entity density, and emotional weight.

**9. Plugin SDK with skill registry**
`from doppelganger.sdk import SkillBase` — subclass it, implement `run()`, drop the folder in `skills/`. The agent discovers it automatically. Community skills are searchable and installable in one command.

**10. iOS/Android companion over LAN**
React Native app that auto-discovers your Doppelganger via mDNS. Full streaming chat, memory search, persona switching, proactive feed. Never touches the internet — pure LAN.

---

## 📦 Installation

### Option 1 — Docker (recommended for everyone)

```bash
git clone https://github.com/stackbleed-ctrl/doppelganger-ai
cd doppelganger-ai
cp .env.example .env
# Open .env and set XAI_API_KEY=your_key_here
docker compose up
```

- Web dashboard: `http://localhost:3000`
- API + docs: `http://localhost:8000/docs`

### Option 2 — Native Python (no Docker)

```bash
# Python 3.11+ and Node 20+ required
pip install uv
uv pip install -e ".[all]"

# Build frontend
cd frontend && npm ci && npm run build && cd ..

# Start
doppelganger start
```

### Option 3 — Desktop app (no Docker, no terminal)

```bash
# Rust, Node 20+, and Python 3.11+ required
./build-desktop.sh

# Output: src-tauri/target/release/bundle/
# macOS  → .dmg
# Windows → .msi and .exe
# Linux  → .deb and .AppImage
```

### Option 4 — Mobile companion

```bash
cd mobile
npm install
npx expo start
# Scan QR code with Expo Go on your phone
# Both devices must be on the same WiFi
```

---

## ⚙️ Configuration

Edit `.env` after copying from `.env.example`:

```bash
# ── Required ──────────────────────────────────────────────────────────────────
XAI_API_KEY=your_xai_api_key_here       # get at console.x.ai

# ── Optional: ports ───────────────────────────────────────────────────────────
API_PORT=8000
FRONTEND_PORT=3000

# ── Optional: security ────────────────────────────────────────────────────────
NEO4J_PASSWORD=doppelganger

# ── Optional: WiFi CSI ────────────────────────────────────────────────────────
ENABLE_WIFI_CSI=false                   # true requires compatible NIC
CSI_INTERFACE=wlan0

# ── Optional: voice ────────────────────────────────────────────────────────────
STT_DEVICE=cpu                          # cpu | cuda

# ── Optional: calendar ────────────────────────────────────────────────────────
GOOGLE_API_KEY=
GOOGLE_CALENDAR_ID=primary
ICAL_URL=

# ── Optional: email skill ─────────────────────────────────────────────────────
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_ADDRESS=you@gmail.com
EMAIL_PASSWORD=your_app_password

# ── Optional: smart home skill ────────────────────────────────────────────────
HOME_ASSISTANT_URL=http://homeassistant.local:8123
HOME_ASSISTANT_TOKEN=your_token

# ── Optional: imports ─────────────────────────────────────────────────────────
NOTION_API_KEY=                         # for Notion memory import
HF_TOKEN=                               # for speaker diarization (pyannote)
```

---

## 🐳 Docker Services

| Service | Purpose | Profile |
|---|---|---|
| `core` | FastAPI orchestrator + agent runtime | always |
| `qdrant` | Vector store (semantic memory search) | always |
| `neo4j` | Knowledge graph (Graphiti) | always |
| `frontend` | React dashboard | always |
| `sensing` | WiFi CSI sensor (privileged) | `--profile wifi-csi` |
| `ollama` | Local embeddings (no API needed) | `--profile ollama` |

```bash
# Standard start
docker compose up

# With WiFi CSI sensing
docker compose --profile wifi-csi up

# With local Ollama embeddings
docker compose --profile ollama up
```

---

## 🔌 Plugin SDK

Build any skill in two files and drop it in `skills/`:

```python
# skills/my_skill/skill.py
from doppelganger.sdk import SkillBase, skill_input, skill_output

class MySkill(SkillBase):
    name = "my_skill"
    description = "Does something useful"

    @skill_input({"query": str})
    @skill_output({"result": str})
    async def run(self, params: dict) -> dict:
        # Built-in SDK helpers:
        # self.ask_grok(prompt)  — call Grok
        # self.remember(text)    — store in memory
        # self.recall(query)     — search memory
        # self.emit(topic, data) — publish event to bus
        result = await self.ask_grok(params["query"])
        await self.remember(f"Ran my_skill: {params['query']}")
        return {"result": result}
```

```json
// skills/my_skill/manifest.json
{
  "name": "my_skill",
  "version": "1.0.0",
  "description": "Does something useful",
  "parameters": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "Input query" }
    },
    "required": ["query"]
  }
}
```

**Scaffold, search, install, publish:**

```bash
doppelganger registry scaffold my_skill --description "Does something useful"
doppelganger registry search
doppelganger registry install weather
doppelganger registry publish skills/my_skill --api-key YOUR_KEY
```

### Built-in skills

| Skill | What it does |
|---|---|
| `email_autoreply` | Reads IMAP inbox, drafts smart replies, optionally sends |
| `smart_home` | Controls Home Assistant — lights, thermostat, switches, covers |
| `minecraft_assistant` | Crafting recipes, mob strategies, build planning (v1.21) |

---

## 💬 CLI Reference

```bash
doppelganger start                          # start the daemon
doppelganger start --no-voice --no-csi      # headless mode

doppelganger chat "What should I focus on today?"   # streaming chat
doppelganger chat "Summarize my week" --no-stream   # non-streaming

doppelganger memory search "last week's projects"
doppelganger memory timeline --hours 48
doppelganger memory store "I decided to learn Rust"
doppelganger memory import --source obsidian --vault ~/notes
doppelganger memory import --source notion
doppelganger memory import --source browser --days 30

doppelganger simulate "What if I move to a new city?" --worlds 4 --steps 6

doppelganger skills                         # list installed skills
doppelganger registry search                # browse registry
doppelganger registry install skill_name
```

---

## 🎭 Personas

| Persona | Style | Auto-triggers |
|---|---|---|
| **Doppelganger** | Direct, balanced, no filler | Default |
| **Work Mode** | Analytical, brief, bullet points, no small talk | meeting, standup, deadline, project |
| **Personal Mode** | Warm, casual, curious, asks follow-up questions | evening, home, family, weekend |
| **Focus Mode** | Minimal, pure signal, one sentence max | focus, deep work, coding, no interruptions |

Create custom personas in the dashboard. Auto-switching triggers on 2+ keyword matches in speech or text.

---

## 🌐 Voice System

| Feature | Backend | Fallback |
|---|---|---|
| STT (speech to text) | faster-whisper — 99 languages, local | — |
| Wake word | openWakeWord (neural ONNX model) | Whisper tiny keyword match → energy threshold |
| TTS (text to speech) | Kokoro (English) · Piper (multilingual) | gTTS (requires internet) |
| Speaker diarization | pyannote.audio (needs HF_TOKEN) | Energy-based segmentation |
| Emotion detection | SpeechBrain IEMOCAP model | Prosodic rule-based analysis |
| Language detection | Whisper built-in | langdetect |

Say **"Hey Doppelganger"** to activate hands-free.

---

## 🧠 Memory System

| Tier | Age | What happens |
|---|---|---|
| **Hot** | 0 – 24h | Full fidelity, verbatim storage |
| **Warm** | 1 – 7 days | Clusters compressed to 3-sentence Grok summaries |
| **Cold** | 7+ days | Entity + relationship graph only, episode content archived |

**Import your existing data into memory:**

```bash
# Obsidian vault — reads all markdown, frontmatter, wiki-links
doppelganger memory import --source obsidian --vault /path/to/vault

# Notion — full page traversal via Notion API
doppelganger memory import --source notion

# Browser history — Chrome, Firefox, Safari (local SQLite, no upload)
doppelganger memory import --source browser --days 30
```

**Visualize:** The dashboard Memory tab includes a live force-directed graph. Nodes colored by entity type. Drag, zoom, click to inspect connections.

---

## 🧪 Testing

```bash
# Full suite
pytest tests/ -v

# Unit tests
pytest tests/test_core.py -v

# End-to-end
pytest tests/e2e/ -v --timeout=60

# Security audit
pytest tests/security/ -v

# Coverage report
pytest tests/ --cov=src --cov-report=html
open htmlcov/index.html
```

---

## 🛣️ What's Been Built

### v0.1.0 — Foundation ✅
Async event bus · Grok-3 streaming + tool calling · parallel world simulation · temporal memory · Qdrant vector search · faster-whisper STT · Kokoro/Piper TTS · WiFi CSI sensing · 3 built-in skills · React/Vite dashboard · Docker Compose · REST + WebSocket + SSE · CLI

### v0.2.0 — Intelligence ✅
Graphiti temporal knowledge graph (Neo4j) · persona system with auto-switching · proactive suggestions engine · Tauri native desktop app

### v0.3.0 — Memory ✅
Memory compression + importance scoring · entity extraction (NER) · force-directed graph visualization · Obsidian + Notion + browser history import

### v0.4.0 — Perception ✅
CSI pose estimation (FFT breathing, activity, gesture) · typing cadence stress estimation · Google Calendar + iCal integration

### v0.5.0 — Voice ✅
Wake word detection · speaker diarization (multi-person) · voice emotion detection · 99-language multilingual support

### v1.0.0 — Stable Release ✅
Plugin SDK with SkillBase class · GitHub skill registry (search, install, publish) · iOS/Android React Native companion · 30+ end-to-end tests · full security audit · SECURITY.md threat model

---

## 🔒 Security & Privacy

**Privacy guarantee:**
- All data stays local — memory, knowledge graph, conversation history never leave your machine
- The only outbound network call is Grok inference via `XAI_API_KEY` (swappable with local Ollama)
- No analytics, no crash reporting, no telemetry of any kind

**Harden your installation:**
```bash
# Require authentication for all API requests
echo "DOPPELGANGER_INTERFACE__API_KEY=$(openssl rand -hex 32)" >> .env

# Restrict to localhost only (already default)
echo "DOPPELGANGER_INTERFACE__HOST=127.0.0.1" >> .env
```

See [SECURITY.md](SECURITY.md) for the full threat model, known limitations, and hardening checklist.

---

## 🤝 Contributing

The fastest contribution: **build a skill** and submit a PR.

```
skills/your_skill/
├── manifest.json
└── skill.py
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions, testing requirements, and the PR checklist.

**Every contributor who ships a skill becomes a maintainer.**

---

<div align="center">

Built with [Grok-3](https://x.ai) · [faster-whisper](https://github.com/SYSTRAN/faster-whisper) · [Kokoro TTS](https://github.com/hexgrad/kokoro) · [Qdrant](https://qdrant.tech) · [Neo4j](https://neo4j.com) · [Tauri](https://tauri.app) · [Expo](https://expo.dev)

**MIT License** — do whatever you want with it.

⭐ Star this repo if you believe AI should run on your hardware — not theirs.

</div>
