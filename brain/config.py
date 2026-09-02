"""Lydia configuration loader and manager."""
from __future__ import annotations
import copy
import os
from pathlib import Path
from typing import Any

import yaml

_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
_ENV_PATH = Path(__file__).parent.parent / ".env"


def load_dotenv() -> dict[str, str]:
    """Parse .env file manually (no python-dotenv dependency required).

    Single source of truth for .env parsing — web.py, stt.py, tts.py and
    wake.py should import this instead of copy-pasting their own parser.
    """
    env: dict[str, str] = {}
    if not _ENV_PATH.exists():
        return env
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _provider_env_key(provider_key: str) -> str:
    """Map provider key to expected .env variable name."""
    return {
        "deepseek": "DEEPSEEK_API_KEY",
        "kimi": "KIMI_API_KEY",
        "groq": "GROQ_API_KEY",
    }.get(provider_key.lower(), f"{provider_key.upper()}_API_KEY")


def load_config() -> dict[str, Any]:
    """Load config.yaml from project root, overlaying API keys from .env if present."""
    if not _CONFIG_PATH.exists():
        cfg = default_config()
    else:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or default_config()

    env = load_dotenv()
    for key in cfg.get("providers", {}):
        env_key = _provider_env_key(key)
        if env_key in env and env[env_key]:
            cfg["providers"][key]["api_key"] = env[env_key]

    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    """Save config.yaml to project root.

    API keys are intentionally stripped before writing — they live in .env
    only. This stops things like set_active_provider() from persisting key
    material back into config.yaml.
    """
    to_save = copy.deepcopy(cfg)
    for key in to_save.get("providers", {}):
        to_save["providers"][key].pop("api_key", None)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(to_save, f, default_flow_style=False, sort_keys=False)


def default_config() -> dict[str, Any]:
    """Return a sensible API-only default configuration."""
    return {
        "lydia": {
            "name": "Lydia",
            "personality": (
                "You are Lydia, a sharp, direct, and capable coding assistant and work partner. "
                "You live on the user's Windows PC. You help with code, system tasks, research, "
                "and automation. Keep responses concise unless detail is requested."
            ),
        },
        "brain": {
            "active_provider": "kimi",
            "temperature": 1.0,
            "max_tool_loops": 15,
        },
        "providers": {
            "deepseek": {
                "type": "openai",
                "label": "DeepSeek",
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "",
            },
            "kimi": {
                "type": "openai",
                "label": "Kimi",
                "model": "kimi-k3",
                "base_url": "https://api.moonshot.cn/v1",
                "api_key": "",
            },
            "groq": {
                "type": "openai",
                "label": "Groq",
                "model": "llama-3.3-70b-versatile",
                "base_url": "https://api.groq.com/openai/v1",
                "api_key": "",
            },
        },
        "context": {"max_messages": 24, "summarize_after": 16},
        "memory": {
            "db_path": "memory_data/memory.db",
            "chroma_path": "memory_data/chroma",
            "top_k": 3,
        },
        "stt": {
            "provider": "local",
            "model": "small",
            "fallbacks": [
                {"provider": "gemini", "model": "gemini-3.6-flash"},
                {"provider": "groq", "model": "whisper-large-v3-turbo"},
            ],
        },
        "tts": {
            "provider": "edge",
            "voice": "en-US-AriaNeural",
            "speed": "+0%",
        },
        "ui": {"host": "127.0.0.1", "port": 8765},
        "vision": {
            "provider": "kimi",
            "model": "kimi-latest",
        },
    }


def get_active_provider() -> dict[str, Any]:
    """Return the active provider configuration."""
    cfg = load_config()
    key = cfg.get("brain", {}).get("active_provider", "kimi")
    return cfg.get("providers", {}).get(key, {})


def set_active_provider(key: str) -> bool:
    """Switch the active provider if it exists."""
    cfg = load_config()
    if key not in cfg.get("providers", {}):
        return False
    cfg.setdefault("brain", {})["active_provider"] = key
    save_config(cfg)
    return True


def get_providers() -> dict[str, Any]:
    """Return all configured providers."""
    return load_config().get("providers", {})
