# Doppelganger Roadmap

## ✅ v0.1.0 — Foundation
- [x] Async priority event bus with wildcard subscriptions
- [x] Grok-3 client — streaming, tool calling, structured JSON output
- [x] Parallel world simulation engine (LangGraph Swarm pattern)
- [x] Temporal memory graph (JSON + Qdrant vector search)
- [x] faster-whisper STT (local, all languages)
- [x] Kokoro + Piper TTS
- [x] WiFi CSI sensing with graceful fallback to simulation
- [x] Skills marketplace — email_autoreply, smart_home, minecraft_assistant
- [x] React/Vite dashboard with dark terminal aesthetic
- [x] Docker Compose one-command install (6 services)
- [x] REST API + SSE streaming + WebSocket event bridge
- [x] Typer + Rich CLI
- [x] GitHub Actions CI

## ✅ v0.2.0 — Intelligence
- [x] Graphiti temporal knowledge graph — Neo4j-backed, bi-temporal versioning
- [x] Persona system — Work / Personal / Focus + custom, auto-switching on keyword triggers
- [x] Proactive suggestions engine — morning briefs, evening summaries, pattern insights, goal nudges
- [x] Tauri native desktop app — Rust process manager, system tray, hide-to-tray, IPC bridge

## ✅ v0.3.0 — Memory
- [x] Memory compression and summarization — importance scoring, warm/cold tiers, Grok compression
- [x] Entity extraction — fast regex NER + deep Grok NER with relationship detection
- [x] Force-directed memory graph visualization — D3 canvas, drag/zoom/filter/click
- [x] Obsidian vault importer — recursive markdown, frontmatter, wiki-link relationships
- [x] Notion importer — API v3, recursive block traversal, tag extraction
- [x] Browser history importer — Chrome/Firefox/Safari SQLite, domain clustering, local-only

## ✅ v0.4.0 — Perception
- [x] CSI pose estimation — FFT breathing rate, heart rate, activity classification, gesture detection, body direction
- [x] Typing cadence stress estimator — IKI variance, WPM, error rate, burst analysis, pynput integration
- [x] Calendar integration — Google Calendar API v3 + iCal parser, proactive context injection, 15-min sync

## ✅ v0.5.0 — Voice
- [x] Wake word detection — openWakeWord neural model + Whisper tiny fallback + energy threshold
- [x] Speaker diarization — pyannote.audio 3.1 + energy fallback, speaker naming, multi-person household
- [x] Voice emotion detection — SpeechBrain IEMOCAP + prosodic rule-based, arousal/valence output
- [x] Multilingual — 99 languages auto-detected, Kokoro/Piper/gTTS routing, per-utterance language switch

## ✅ v1.0.0 — Stable Release
- [x] Plugin SDK — SkillBase class, @skill_input/@skill_output/@requires_env/@cached decorators
- [x] Skill scaffolder — 4-file template generated from CLI
- [x] Skill registry — GitHub topic discovery + official registry API client, search/install/publish
- [x] iOS/Android companion — React Native + Expo, mDNS auto-discovery, LAN-only, full API
- [x] End-to-end test suite — 30+ tests: health, chat, streaming, memory CRUD, persona lifecycle, simulation, WebSocket, concurrency
- [x] Security audit — prompt injection, path traversal, XSS in memory, null bytes, unicode, large payloads, data isolation, information disclosure
- [x] SECURITY.md — threat model, known limitations, hardening checklist, vulnerability reporting

---

## 🔜 Post-v1.0 Ideas

These are community suggestions and internal ideas — not committed to any timeline.

**Multi-user household mode**
Separate knowledge graphs per detected speaker. Family members each get their own Doppelganger context. Requires diarization + speaker profile training.

**Offline-first mode**
Replace Grok with a fully local model (Llama 3.1 / Mistral / Qwen via Ollama). Eliminates the only external network dependency. Trade-off: slower inference, lower quality on complex reasoning.

**Raspberry Pi 5 image**
Pre-built `.img` for RPi5 — plug in, connect to WiFi, scan QR code, done. Makes Doppelganger a dedicated always-on household device.

**Plugin marketplace website**
A proper registry.doppelganger.ai with skill browsing, ratings, verified author badges, and one-click install from the dashboard.

**Calendar write-back**
Voice command "schedule a meeting with Alex next Tuesday at 2pm" → creates the event. Requires OAuth flow for Google Calendar.

**Browser extension**
Chrome/Firefox sidebar that connects to your local Doppelganger. Summarizes pages, stores them to memory, answers questions about what you're reading.

**Fine-tuning on personal data**
Opt-in LoRA fine-tuning on your conversation history and memory graph. Fully local via llama.cpp or MLX. Makes the model genuinely reflect your writing style and knowledge.

**Webhook skill triggers**
Inbound webhooks as skill triggers — "when a GitHub PR is opened, brief me". Replaces polling-based integrations with event-driven ones.
