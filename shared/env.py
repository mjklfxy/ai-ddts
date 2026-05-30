"""Environment-aware configuration path resolution."""

from __future__ import annotations

import os
from pathlib import Path


def get_env() -> str:
    """Returns current environment identifier: 'dev' (default) or 'prod'."""
    return os.getenv("APP_ENV", "dev")


def resolve_config_path() -> Path:
    """Resolves config file path based on APP_ENV.

    Reads config/config.{APP_ENV}.json if it exists,
    otherwise falls back to config/config.json.
    """
    env = get_env()
    p = Path("config") / f"config.{env}.json"
    return p if p.exists() else Path("config") / "config.json"


def is_channel_classification_enabled() -> bool:
    """Returns whether the channel_classification column is enabled.

    Controlled by env var AI_DDTS_CHANNEL_CLASSIFICATION_ENABLED.
    Defaults to True when unset.
    """
    return os.getenv("AI_DDTS_CHANNEL_CLASSIFICATION_ENABLED", "1").strip().lower() in (
        "1", "true", "yes",
    )


def load_dotenv(path: Path = Path(".env")) -> None:
    """Loads .env file into os.environ without adding a dependency.

    Existing environment variables are not overwritten (os.environ.setdefault).
    """
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())
