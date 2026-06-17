"""
Server type registry.

Each server-type package (``nuxeo/``, ``alfresco/``, …) registers its own
configuration here.  The ``drive/`` layer queries this registry instead of
hard-coding server-specific values.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class ServerTypeConfig:
    """Configuration contributed by a server-type package."""

    key: str  # e.g. "NUXEO", "ALFRESCO"
    home_dir: str  # e.g. ".nuxeo-drive", ".alfresco-drive"
    log_file: str  # e.g. "nxdrive.log", "aldrive.log"
    db_prefix: str  # e.g. "ndrive_", "adrive_"
    engine_type: str  # engine type key e.g. "NXDRIVE", "ALFRESCO"
    engine_class_path: str = ""  # e.g. "nxdrive.nuxeo.engine.engine.Engine"
    direct_edit_class_path: str = ""  # e.g. "nxdrive.nuxeo.direct_edit.DirectEdit"
    direct_download_class_path: str = (
        ""  # e.g. "nxdrive.nuxeo.direct_download.DirectDownload"
    )
    workflow_class_path: str = ""  # e.g. "nxdrive.nuxeo.client.workflow.Workflow"
    oauth2_class_path: str = ""  # e.g. "nxdrive.nuxeo.auth.oauth2.OAuthentication"
    folders_only_class_path: str = (
        ""  # e.g. "nxdrive.nuxeo.gui.folders_model.FoldersOnly"
    )
    disabled_features: List[str] = field(default_factory=list)
    auth_factory: Optional[Callable[..., Any]] = None

    # Branding
    app_name: str = "Drive"  # e.g. "Nuxeo Drive", "Alfresco Drive"
    company: str = "Hyland"
    bundle_identifier: str = "com.hyland.drive"  # macOS bundle id
    url_scheme: str = "drive"  # custom URL protocol
    config_registry_key: str = "Software\\\\Hyland\\\\Drive"  # Windows registry
    emblem_name: str = "emblem-drive"  # Linux folder emblem icon name
    local_folder_name: str = "Drive"  # default sync folder name
    download_exe: str = "drive.exe"  # fatal error download filename (Windows)
    download_dmg: str = "drive.dmg"  # fatal error download filename (macOS)
    download_appimage: str = "drive-x86_64.AppImage"  # fatal error download (Linux)

    # Nuxeo-specific (empty for non-Nuxeo server types)
    sync_root: str = ""  # e.g. "/org.nuxeo.drive.service.impl..."
    url_patterns: List[str] = field(default_factory=list)  # URL path suffixes to match

    # SSL validation page to probe when checking server connectivity
    ssl_login_page: str = ""  # e.g. "" (Nuxeo default), "api/discovery" (Alfresco)

    # Whether the server type supports browser-based token update (OAuth2 redirect)
    supports_browser_token_update: bool = True

    # If True, this config is returned by detect_by_url when no url_patterns match
    is_url_fallback: bool = False

    # Version string of the underlying Python client library (e.g. nuxeo.__version__)
    client_version: str = ""

    # Hook called when debug mode is enabled (e.g. to set nuxeo.constants.CHECK_PARAMS)
    debug_init_hook: Optional[Callable[[], None]] = None

    # Hook to re-authenticate when browser-based token update is not supported
    # Signature: relogin_handler(engine, password) -> None
    relogin_handler: Optional[Callable[..., None]] = None

    # Hook for the non-frozen debug auth dialog (server-type specific)
    # Signature: debug_auth_handler(url, manager, api) -> None
    debug_auth_handler: Optional[Callable[..., None]] = None


# ---- internal state --------------------------------------------------------

_registry: Dict[str, ServerTypeConfig] = {}
_default_key: Optional[str] = None


# ---- public API ------------------------------------------------------------


def register(config: ServerTypeConfig, *, default: bool = False) -> None:
    """Register a server-type configuration."""
    _registry[config.key] = config
    if default:
        global _default_key
        _default_key = config.key


def get(key: str) -> ServerTypeConfig:
    """Return the config for *key*, falling back to the default."""
    return _registry.get(key, _registry[_default_key])


def get_default_key() -> str:
    """Return the key of the default server type."""
    return _default_key or next(iter(_registry))


def all_configs() -> Dict[str, ServerTypeConfig]:
    """Return all registered configs."""
    return dict(_registry)


def all_home_dirs() -> Tuple[str, ...]:
    """Return all known home directory names."""
    return tuple(c.home_dir for c in _registry.values())


def all_db_prefixes() -> Tuple[str, ...]:
    """Return all known database file prefixes."""
    return tuple(c.db_prefix for c in _registry.values())


def all_keys() -> Tuple[str, ...]:
    """Return all registered server-type keys."""
    return tuple(_registry.keys())


def get_by_engine_type(engine_type: str) -> ServerTypeConfig:
    """Return the config whose *engine_type* matches, falling back to default."""
    for config in _registry.values():
        if config.engine_type == engine_type:
            return config
    return _registry[_default_key]


def detect_by_url(url: str) -> ServerTypeConfig:
    """Return the config whose *url_patterns* match the URL path suffix.

    Tries each registered config's ``url_patterns`` against the URL
    path (stripped of trailing slashes).  The first match wins.
    If nothing matches, the config with ``is_url_fallback=True`` is
    returned; otherwise the default config is returned.
    """
    from urllib.parse import urlparse

    path = urlparse(url).path.rstrip("/")
    for config in _registry.values():
        for pattern in config.url_patterns:
            if path.endswith(f"/{pattern}") or path == pattern:
                return config
    # Return the fallback config, or the default
    for config in _registry.values():
        if config.is_url_fallback:
            return config
    return _registry[_default_key]


def load_class(class_path: str) -> Optional[type]:
    """Import and return the class at *class_path*, or ``None`` on failure."""
    if not class_path:
        return None
    import importlib

    module_path, class_name = class_path.rsplit(".", 1)
    try:
        module = importlib.import_module(module_path)
        return getattr(module, class_name)
    except (ImportError, AttributeError):
        return None
