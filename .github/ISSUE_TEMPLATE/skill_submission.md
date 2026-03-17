---
name: Skill submission
about: Submit a new skill to the marketplace
labels: skill
---

**Skill name**
`your_skill_name`

**What it does**
One paragraph description.

**Requirements**
- External APIs needed (if any):
- Required env vars:
- Python deps beyond core:

**Checklist**
- [ ] `manifest.json` with complete parameter schema
- [ ] `skill.py` with `async def run(params: dict) -> dict`
- [ ] Handles missing env vars gracefully (returns `{"error": "..."}`)
- [ ] Works offline / doesn't require Grok (or clearly documented that it does)
- [ ] Tested locally via `doppelganger skills`
- [ ] No credentials committed
