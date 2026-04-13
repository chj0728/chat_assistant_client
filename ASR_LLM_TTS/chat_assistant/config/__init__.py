# import logging
from pathlib import Path
from typing import Any

from logger import logger


def get_default_config_path() -> Path:
    """Return the default config.yaml path under this package."""
    return Path(__file__).resolve().parent / "config.yaml"


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load YAML config and always return a dict.

    When loading fails, return an empty dict so callers can safely use
    config.get(..., default) without extra guard code.
    """
    path = Path(config_path) if config_path else get_default_config_path()

    try:
        import yaml

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.error("加载配置文件失败: %s", exc)
        return {}


def print_config(config: dict[str, Any]) -> None:
    """Print the config in a readable format."""
    import yaml

    logger.debug("当前配置:\n%s", yaml.dump(config, allow_unicode=True))
