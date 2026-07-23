from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any

from logger import logger

DEFAULT_MAX_MESSAGES = 5
_CONFIG_CACHE: dict[Path, dict[str, Any]] = {}
_CONFIG_CACHE_LOCK = RLock()
_CONFIG_DIR = Path(__file__).resolve().parent
_PROJECT_CONFIG_PATH = _CONFIG_DIR / "project.toml"
_FALLBACK_CONFIG_PATH = _CONFIG_DIR / "config.toml"


def get_default_config_path() -> Path:
    """Return the active config path selected by project.toml."""
    project_config = _read_config(_PROJECT_CONFIG_PATH)
    active_toml = project_config.get("active_toml", "config.toml")

    if not isinstance(active_toml, str) or not active_toml.strip():
        logger.error("project.toml 中的 active_toml 必须是非空字符串")
        return _FALLBACK_CONFIG_PATH

    active_path = (_CONFIG_DIR / active_toml).resolve()
    if (
        active_path.parent != _CONFIG_DIR
        or active_path.suffix.lower() != ".toml"
        or active_path == _PROJECT_CONFIG_PATH
    ):
        logger.error("project.toml 中的 active_toml 无效: %s", active_toml)
        return _FALLBACK_CONFIG_PATH

    if not active_path.is_file():
        logger.error("project.toml 指定的配置文件不存在: %s", active_path)
        return _FALLBACK_CONFIG_PATH

    return active_path


def get_default_pkg_dir() -> Path:
    """Return the default package directory path."""
    return Path(__file__).resolve().parent.parent


def _resolve_config_path(config_path: str | Path | None = None) -> Path:
    """Resolve config path to an absolute normalized path."""
    path = Path(config_path) if config_path else get_default_config_path()
    return path.expanduser().resolve()


def _read_config(path: Path) -> dict[str, Any]:
    """Read config from disk and normalize to a dict."""
    try:
        if path.suffix.lower() == ".toml":
            try:
                import tomllib
            except ModuleNotFoundError:
                import tomli as tomllib  # type: ignore[import-not-found,no-redef]

            with path.open("rb") as f:
                data = tomllib.load(f)
        else:
            import yaml

            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.error("加载配置文件失败: %s", exc)
        return {}


def load_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load TOML or YAML config and always return a dict.

    The config is cached per path, so repeated calls from other modules do not
    repeatedly read or parse the config file.
    """
    path = _resolve_config_path(config_path)

    with _CONFIG_CACHE_LOCK:
        if path not in _CONFIG_CACHE:
            _CONFIG_CACHE[path] = _read_config(path)

        return deepcopy(_CONFIG_CACHE[path])


def clear_config_cache(config_path: str | Path | None = None) -> None:
    """Clear cached config for one path or all cached config entries."""
    with _CONFIG_CACHE_LOCK:
        if config_path is None:
            _CONFIG_CACHE.clear()
            return

        _CONFIG_CACHE.pop(_resolve_config_path(config_path), None)


def reload_config(config_path: str | Path | None = None) -> dict[str, Any]:
    """Force reload config from disk and refresh the cache."""
    path = _resolve_config_path(config_path)
    config = _read_config(path)

    with _CONFIG_CACHE_LOCK:
        _CONFIG_CACHE[path] = config

    return deepcopy(config)


def print_config(config: dict[str, Any]) -> None:
    """Print the config in a readable format."""
    import yaml

    logger.debug("当前配置:\n%s", yaml.dump(config, allow_unicode=True))


def get_max_messages(default: int = DEFAULT_MAX_MESSAGES) -> int:
    """从配置中读取最大历史消息数，读取失败时回退默认值。"""
    config = load_config()
    max_messages = config.get("llm", {}).get("max_messages", default)
    logger.debug(f"LLM Agent 配置 - MAX_MESSAGES: {max_messages}")
    return max_messages


def get_max_tokens(default: int = 2048) -> int:
    """从配置中读取最大历史消息数，读取失败时回退默认值。"""
    config = load_config()
    max_tokens = config.get("llm", {}).get("max_tokens", default)
    logger.debug(f"LLM Agent 配置 - MAX_TOKENS: {max_tokens}")
    return max_tokens


def get_vad_no_speech_threshold(default: float = 0.5) -> float:
    """从配置中读取VAD无语音阈值(单位: 秒），读取失败时回退默认值。"""
    config = load_config()
    threshold = config.get("VAD", {}).get("no_speech_threshold", default)
    logger.debug(f"ASR 配置 - VAD_NO_SPEECH_THRESHOLD: {threshold} 秒")
    return threshold


def get_default_system_prompt(default: str = "") -> str:
    """从配置中读取默认系统提示词，读取失败时回退默认值。"""
    config = load_config()
    default_system_prompt = config.get("llm", {}).get("default_system_prompt", default)
    logger.debug(f"LLM Agent 配置 - DEFAULT_SYSTEM_PROMPT:\n{default_system_prompt}")
    return default_system_prompt
