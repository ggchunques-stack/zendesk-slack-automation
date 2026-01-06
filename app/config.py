import json
from pathlib import Path
from typing import Any, Dict

from app.settings import get_settings

_MAPPING_CACHE: Dict[str, Any] | None = None
_MAPPING_PATH: str | None = None

def load_mapping() -> Dict[str, Any]:
    global _MAPPING_CACHE, _MAPPING_PATH
    settings = get_settings()
    path = Path(settings.MAPPING_PATH)
    path_key = str(path.resolve())
    if _MAPPING_CACHE is not None and _MAPPING_PATH == path_key:
        return _MAPPING_CACHE
    _MAPPING_CACHE = json.loads(path.read_text(encoding="utf-8"))
    _MAPPING_PATH = path_key
    return _MAPPING_CACHE

def get_route_config(route_to: str) -> Dict[str, Any]:
    mapping = load_mapping()
    allowed_keys = {"group_id", "assignee_id", "slack_channel", "notify_on"}
    if any(key in mapping for key in allowed_keys):
        return {key: mapping[key] for key in allowed_keys if key in mapping}
    route_config = mapping.get(route_to, {})
    if isinstance(route_config, dict):
        return {key: route_config[key] for key in allowed_keys if key in route_config}
    return {}
