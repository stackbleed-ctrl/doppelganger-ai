"""
Minecraft Assistant Skill
Answers Minecraft questions using Grok with version-aware context.
No external APIs needed — pure LLM knowledge.
"""

from __future__ import annotations


SYSTEM_PROMPT = """\
You are an expert Minecraft assistant with encyclopedic knowledge of the game through version 1.21.
You give precise, actionable answers. For crafting recipes, use the grid format:
  [item][item][item]
  [item][item][item]  →  [result]
  [item][item][item]
For mob strategies, give HP, drops, and combat tips.
For builds, give material lists and step-by-step instructions.
Be concise. No fluff."""


MODE_PROMPTS = {
    "recipe": "Focus on the crafting recipe, ingredients, and any variants or alternatives.",
    "mob": "Cover HP, attack damage, drops, spawn conditions, and combat strategy.",
    "build": "Provide a material list, dimensions, and step-by-step build instructions.",
    "biome": "Describe the biome's features, unique resources, mobs, and how to find it.",
    "general": "",
}


async def run(params: dict) -> dict:
    query = params.get("query", "")
    mode = params.get("mode", "general")
    version = params.get("version", "1.21")

    if not query:
        return {"error": "query is required"}

    mode_hint = MODE_PROMPTS.get(mode, "")
    user_prompt = f"Minecraft {version} — {query}"
    if mode_hint:
        user_prompt += f"\n\n{mode_hint}"

    try:
        from doppelganger.agents.grok_client import get_grok
        grok = get_grok()

        response = await grok.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=800,
        )

        return {
            "query": query,
            "mode": mode,
            "version": version,
            "answer": response,
        }

    except Exception as e:
        return {"error": f"Grok request failed: {e}"}
