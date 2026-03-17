"""
Doppelganger Configuration
Pydantic-based settings with environment variable overrides.
Load order: defaults → config/default.yaml → config/user.yaml → env vars
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ─── Sub-models ──────────────────────────────────────────────────────────────


class GrokSettings(BaseModel):
    api_key: str = Field(default="", description="xAI API key — set XAI_API_KEY env var")
    base_url: str = "https://api.x.ai/v1"
    model: str = "grok-3-latest"
    max_tokens: int = 4096
    temperature: float = 0.7
    streaming: bool = True


class MemorySettings(BaseModel):
    backend: Literal["qdrant", "chroma"] = "qdrant"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "doppelganger"
    graphiti_neo4j_url: str = "bolt://neo4j:7687"
    graphiti_neo4j_user: str = "neo4j"
    graphiti_neo4j_password: str = "doppelganger"
    embedding_model: str = "nomic-embed-text"
    short_term_capacity: int = 128  # events before compression
    long_term_ttl_days: int = 365


class VoiceSettings(BaseModel):
    stt_model: str = "base"          # faster-whisper model size
    stt_device: Literal["cpu", "cuda", "auto"] = "auto"
    stt_compute_type: str = "int8"
    tts_engine: Literal["piper", "kokoro"] = "kokoro"
    tts_voice: str = "af_sky"        # Kokoro voice id
    vad_threshold: float = 0.5       # voice activity detection
    sample_rate: int = 16000
    chunk_duration_ms: int = 30


class PerceptionSettings(BaseModel):
    enable_wifi_csi: bool = False    # requires privileged container + compatible NIC
    enable_microphone: bool = True
    enable_system_metrics: bool = True
    csi_interface: str = "wlan0"
    presence_threshold: float = 0.6
    metrics_interval_sec: float = 5.0


class ReasoningSettings(BaseModel):
    max_parallel_worlds: int = 4
    world_sim_steps: int = 8
    planner_model: str = "grok-3-latest"
    enable_counterfactuals: bool = True


class InterfaceSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    ws_heartbeat_sec: float = 15.0
    api_key: str = ""                # optional - leave empty for local-only


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DOPPELGANGER_",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    version: str = "0.1.0"
    debug: bool = False
    log_level: str = "INFO"
    data_dir: Path = Path("~/.doppelganger").expanduser()

    grok: GrokSettings = Field(default_factory=GrokSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    perception: PerceptionSettings = Field(default_factory=PerceptionSettings)
    reasoning: ReasoningSettings = Field(default_factory=ReasoningSettings)
    interface: InterfaceSettings = Field(default_factory=InterfaceSettings)

    def __init__(self, **kwargs):
        # Merge YAML configs before env vars win
        yaml_data = _load_yaml_configs()
        merged = {**yaml_data, **kwargs}
        # xAI API key shortcut
        if not merged.get("grok", {}).get("api_key"):
            api_key = os.environ.get("XAI_API_KEY", "")
            if api_key:
                merged.setdefault("grok", {})["api_key"] = api_key
        super().__init__(**merged)
        self.data_dir.mkdir(parents=True, exist_ok=True)


def _load_yaml_configs() -> dict:
    config_dir = Path("config")
    merged: dict = {}
    for fname in ("default.yaml", "user.yaml"):
        p = config_dir / fname
        if p.exists():
            with p.open() as f:
                data = yaml.safe_load(f) or {}
            _deep_merge(merged, data)
    return merged


def _deep_merge(base: dict, override: dict) -> dict:
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
    return base


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
