# Security Policy

## Doppelganger Security Model

Doppelganger is designed as a **local-first, privacy-first** system. This shapes our entire security model.

## Core Security Properties

### 1. No external data exfiltration
- All LLM inference goes to xAI Grok API (configurable to local Ollama)
- Memory, knowledge graph, and user data never leave the local machine
- No analytics, no telemetry, no cloud sync

### 2. Network exposure
- By default, the API binds to `127.0.0.1` (localhost only)
- Docker Compose exposes port 8000 — do not expose this to the public internet without authentication
- The mobile companion communicates LAN-only via direct IP

### 3. Skill sandbox model
- Skills run in the same Python process as the core (not truly sandboxed)
- **For production use, run the entire system in Docker** — this provides OS-level isolation
- Skills are reviewed before being listed in the public registry
- Never install skills from untrusted sources

### 4. API key protection
- The `XAI_API_KEY` is stored in `.env` (gitignored by default)
- Never commit `.env` to version control
- The optional `DOPPELGANGER_INTERFACE__API_KEY` can be set to require bearer token auth

## Known Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| Skills share process | A malicious skill can read memory | Use Docker, review skill code before installing |
| No TLS by default | LAN traffic is unencrypted | Use a reverse proxy (nginx + self-signed cert) for sensitive deployments |
| API key in env vars | Readable by other processes | Use a secrets manager in production |
| Memory stored as JSON | No encryption at rest | Encrypt the data directory (`~/.doppelganger`) with OS-level disk encryption |
| WebSocket no auth | Anyone on LAN can connect | Set `DOPPELGANGER_INTERFACE__API_KEY` to require authentication |

## Reporting Vulnerabilities

Please report security vulnerabilities privately:

1. **GitHub Security Advisories**: `https://github.com/doppelganger-ai/doppelganger/security/advisories/new`
2. **Email**: security@doppelganger.ai (PGP key available on keyserver)

Do **not** open public GitHub issues for security vulnerabilities.

We aim to respond within 72 hours and patch within 14 days.

## Scope

In scope:
- Remote code execution via API
- Data exfiltration via API responses
- Authentication bypass
- Path traversal in skill/import endpoints
- Prompt injection leading to unintended actions

Out of scope:
- Social engineering
- Physical access attacks
- Vulnerabilities in third-party dependencies (report upstream)
- Self-XSS (the dashboard is a local app)

## Security Hardening Checklist

For production/sensitive deployments:

```bash
# 1. Set API key
echo "DOPPELGANGER_INTERFACE__API_KEY=$(openssl rand -hex 32)" >> .env

# 2. Bind to localhost only (already default)
echo "DOPPELGANGER_INTERFACE__HOST=127.0.0.1" >> .env

# 3. Encrypt data directory
# macOS: System Settings → Privacy & Security → FileVault
# Linux: Use LUKS or eCryptfs on ~/.doppelganger

# 4. Review installed skills
ls skills/
cat skills/*/manifest.json

# 5. Use Docker for skill isolation (recommended)
docker compose up  # skills run in isolated container
```
