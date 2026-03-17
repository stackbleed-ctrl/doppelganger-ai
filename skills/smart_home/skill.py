"""
Smart Home Skill
Controls Home Assistant devices via REST API.
Set HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN env vars.
"""

from __future__ import annotations

import os
import httpx

HA_URL = os.environ.get("HOME_ASSISTANT_URL", "http://homeassistant.local:8123")
HA_TOKEN = os.environ.get("HOME_ASSISTANT_TOKEN", "")

HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}


async def _ha_get(path: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{HA_URL}/api/{path}", headers=HEADERS)
        resp.raise_for_status()
        return resp.json()


async def _ha_post(path: str, data: dict) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(f"{HA_URL}/api/{path}", json=data, headers=HEADERS)
        resp.raise_for_status()
        return resp.json()


async def run(params: dict) -> dict:
    if not HA_TOKEN:
        return {"error": "HOME_ASSISTANT_TOKEN not set"}

    action = params.get("action", "list_devices")
    entity_id = params.get("entity_id", "")

    try:
        if action == "list_devices":
            states = await _ha_get("states")
            devices = [
                {
                    "entity_id": s["entity_id"],
                    "state": s["state"],
                    "name": s.get("attributes", {}).get("friendly_name", s["entity_id"]),
                }
                for s in states
                if s["entity_id"].split(".")[0] in ("light", "switch", "climate", "media_player", "cover")
            ]
            return {"devices": devices, "count": len(devices)}

        elif action == "get_state":
            if not entity_id:
                return {"error": "entity_id required"}
            state = await _ha_get(f"states/{entity_id}")
            return {
                "entity_id": entity_id,
                "state": state["state"],
                "attributes": state.get("attributes", {}),
            }

        elif action in ("turn_on", "turn_off", "toggle"):
            if not entity_id:
                return {"error": "entity_id required"}
            service_data: dict = {"entity_id": entity_id}
            if action == "turn_on":
                if "brightness" in params:
                    service_data["brightness"] = params["brightness"]
                if "temperature" in params:
                    service_data["temperature"] = params["temperature"]
            domain = entity_id.split(".")[0]
            result = await _ha_post(f"services/{domain}/{action}", service_data)
            return {"success": True, "action": action, "entity_id": entity_id}

        elif action == "set_brightness":
            if not entity_id:
                return {"error": "entity_id required"}
            brightness = params.get("brightness", 128)
            result = await _ha_post("services/light/turn_on", {
                "entity_id": entity_id,
                "brightness": brightness,
            })
            return {"success": True, "entity_id": entity_id, "brightness": brightness}

        elif action == "set_temperature":
            if not entity_id:
                return {"error": "entity_id required"}
            temp = params.get("temperature")
            if temp is None:
                return {"error": "temperature required"}
            result = await _ha_post("services/climate/set_temperature", {
                "entity_id": entity_id,
                "temperature": temp,
            })
            return {"success": True, "entity_id": entity_id, "temperature": temp}

        else:
            return {"error": f"Unknown action: {action}"}

    except httpx.HTTPStatusError as e:
        return {"error": f"Home Assistant API error: {e.response.status_code}"}
    except Exception as e:
        return {"error": str(e)}
