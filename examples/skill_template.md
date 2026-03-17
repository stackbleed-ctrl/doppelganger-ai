# Doppelganger Skill Template
#
# Copy this folder, rename it, fill in the two files below.
# The agent will auto-discover your skill on next restart.

## manifest.json

```json
{
  "name": "my_skill",
  "version": "1.0.0",
  "description": "What your skill does — be specific, the LLM reads this.",
  "author": "your-github-handle",
  "timeout_sec": 30,
  "parameters": {
    "type": "object",
    "properties": {
      "input": {
        "type": "string",
        "description": "Describe what this param does"
      },
      "mode": {
        "type": "string",
        "enum": ["option_a", "option_b"],
        "default": "option_a",
        "description": "Optional enum param"
      }
    },
    "required": ["input"]
  },
  "permissions": []
}
```

## skill.py

```python
"""
My Skill
One-line description.
"""

async def run(params: dict) -> dict:
    """
    Main skill entrypoint.
    Always return a dict.
    Raise exceptions freely — the loader catches them.
    """
    input_val = params.get("input", "")
    mode = params.get("mode", "option_a")

    if not input_val:
        return {"error": "input is required"}

    # Do your thing
    result = f"Processed: {input_val} (mode={mode})"

    return {
        "result": result,
        "input": input_val,
        "mode": mode,
    }
```

## Tips

- Use `from doppelganger.agents.grok_client import get_grok` for LLM access
- Use `httpx.AsyncClient` for external HTTP calls
- Store credentials in env vars, read with `os.environ.get(...)`
- `timeout_sec` in manifest enforces a hard deadline
- Return `{"error": "..."}` for expected failures, raise for unexpected ones
- Test locally: `doppelganger skills` then expand your skill in the dashboard
