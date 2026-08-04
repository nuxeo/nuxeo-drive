"""Nuxeo-specific persistence for browser authentication callback context."""

import json
from typing import Any, Dict

_PENDING_AUTH_CALLBACK_KEY = "tmp_auth_callback_params"


def save_auth_callback_params(api: "Any", params: Dict[str, str], /) -> None:
    """Persist callback params to survive async browser callback timing."""
    api._manager.dao.update_config(_PENDING_AUTH_CALLBACK_KEY, json.dumps(params))


def load_auth_callback_params(api: "Any", /) -> Dict[str, str]:
    """Load and decode persisted callback params."""
    raw = api._manager.dao.get_config(_PENDING_AUTH_CALLBACK_KEY)
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def clear_auth_callback_params(api: "Any", /) -> None:
    """Clear persisted callback params once callback has been processed."""
    api._manager.dao.delete_config(_PENDING_AUTH_CALLBACK_KEY)
