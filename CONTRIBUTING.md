# Contributing to Doppelganger

Thanks for making Doppelganger better. This is a local-first, privacy-first project
and we want to keep it that way.

## Quickest contribution: Add a skill

Drop a folder into `skills/` with two files:

```
skills/your_skill_name/
├── manifest.json   ← metadata + parameter schema
└── skill.py        ← async def run(params: dict) -> dict
```

**manifest.json minimum:**
```json
{
  "name": "your_skill_name",
  "version": "1.0.0",
  "description": "What this skill does",
  "parameters": {
    "type": "object",
    "properties": {
      "input": { "type": "string", "description": "..." }
    },
    "required": ["input"]
  }
}
```

**skill.py minimum:**
```python
async def run(params: dict) -> dict:
    # do something
    return {"result": "..."}
```

That's it. Submit a PR. Skills are the lifeblood of this project.

---

## Bigger contributions

### Setup

```bash
git clone https://github.com/doppelganger-ai/doppelganger
cd doppelganger
pip install uv
uv pip install -e ".[dev]"
```

### Run tests

```bash
pytest tests/ -v
```

### Lint + type check

```bash
ruff check src/
mypy src/
```

### Run locally (no Docker)

```bash
cp .env.example .env
# add your XAI_API_KEY to .env
python -m doppelganger.interfaces.cli start --no-csi
```

### Project conventions

- **Async everywhere**: all I/O is `async/await`
- **Event-driven**: use the bus, don't call layers directly
- **Fail gracefully**: optional hardware/deps must degrade cleanly
- **Local-first**: no telemetry, no mandatory cloud calls
- **Type hints**: all public functions must be typed

### PR checklist

- [ ] New skill OR bug fix OR feature
- [ ] Tests added/updated
- [ ] `ruff check` passes
- [ ] Docs updated if API changed
- [ ] Privacy contract maintained (no data leaves the machine without explicit user action)

## Code of conduct

Be excellent to each other.
