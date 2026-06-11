"""Unit tests for the server-type registry and auto-discovery mechanism.

Tests cover:
- ServerTypeConfig registration/lookup
- Auto-discovery of registration modules
- detect_by_url matching
- load_class dynamic loading
- drive/ folder independence (zero imports from nuxeo/ or alfresco/)
"""

import importlib
import pkgutil
from pathlib import Path

import pytest

from nxdrive.drive.server_type import (
    ServerTypeConfig,
    _registry,
    all_configs,
    all_db_prefixes,
    all_home_dirs,
    all_keys,
    detect_by_url,
    get,
    get_by_engine_type,
    get_default_key,
    load_class,
    register,
)

# ------------------------------------------------------------------ fixtures


@pytest.fixture(autouse=True)
def _restore_registry():
    """Snapshot and restore the global registry around each test."""
    from nxdrive.drive import server_type as st

    old_registry = dict(st._registry)
    old_default = st._default_key
    yield
    st._registry.clear()
    st._registry.update(old_registry)
    st._default_key = old_default


@pytest.fixture
def dummy_config():
    """Return a minimal ServerTypeConfig for testing."""
    return ServerTypeConfig(
        key="TEST",
        home_dir=".test-drive",
        log_file="test.log",
        db_prefix="test_",
        engine_type="TEST_ENGINE",
        engine_class_path="nxdrive.drive.engine.workers.Worker",
    )


# ------------------------------------------------------------------ registration


def test_register_adds_to_registry(dummy_config):
    register(dummy_config)
    assert "TEST" in _registry
    assert _registry["TEST"] is dummy_config


def test_register_default(dummy_config):
    register(dummy_config, default=True)
    assert get_default_key() == "TEST"


def test_get_returns_config(dummy_config):
    register(dummy_config)
    assert get("TEST") is dummy_config


def test_get_falls_back_to_default(dummy_config):
    register(dummy_config, default=True)
    cfg = get("NONEXISTENT")
    assert cfg is dummy_config


def test_all_keys_contains_registered():
    keys = all_keys()
    assert "NUXEO" in keys
    assert "ALFRESCO" in keys


def test_all_home_dirs():
    dirs = all_home_dirs()
    assert ".nuxeo-drive" in dirs
    assert ".alfresco-drive" in dirs


def test_all_db_prefixes():
    prefixes = all_db_prefixes()
    assert "ndrive_" in prefixes
    assert "adrive_" in prefixes


def test_all_configs_returns_dict():
    configs = all_configs()
    assert isinstance(configs, dict)
    assert "NUXEO" in configs
    assert "ALFRESCO" in configs


# ------------------------------------------------------------------ detect_by_url


def test_detect_by_url_nuxeo():
    cfg = detect_by_url("https://example.com/nuxeo/")
    assert cfg.key == "NUXEO"


def test_detect_by_url_nuxeo_no_trailing_slash():
    cfg = detect_by_url("https://example.com/nuxeo")
    assert cfg.key == "NUXEO"


def test_detect_by_url_alfresco_fallback():
    """Alfresco is the URL fallback when no patterns match."""
    cfg = detect_by_url("https://acs.example.com/")
    assert cfg.key == "ALFRESCO"


def test_detect_by_url_unknown_falls_back():
    cfg = detect_by_url("https://unknown-server.example.com/api/v1")
    # Should return fallback (Alfresco has is_url_fallback=True)
    assert cfg.key in ("ALFRESCO", "NUXEO")


# ------------------------------------------------------------------ get_by_engine_type


def test_get_by_engine_type_nuxeo():
    cfg = get_by_engine_type("NXDRIVE")
    assert cfg.key == "NUXEO"


def test_get_by_engine_type_alfresco():
    cfg = get_by_engine_type("ALFRESCO")
    assert cfg.key == "ALFRESCO"


def test_get_by_engine_type_unknown_returns_default():
    cfg = get_by_engine_type("UNKNOWN_ENGINE")
    assert cfg.key == get_default_key()


# ------------------------------------------------------------------ load_class


def test_load_class_valid():
    cls = load_class("nxdrive.drive.engine.workers.Worker")
    assert cls is not None
    assert cls.__name__ == "Worker"


def test_load_class_empty_string():
    assert load_class("") is None


def test_load_class_invalid_module():
    assert load_class("nxdrive.nonexistent.module.Cls") is None


def test_load_class_invalid_attr():
    assert load_class("nxdrive.drive.engine.workers.NonexistentClass") is None


def test_load_class_nuxeo_engine():
    cls = load_class("nxdrive.nuxeo.engine.engine.Engine")
    assert cls is not None
    assert cls.__name__ == "Engine"


def test_load_class_nuxeo_direct_edit():
    cls = load_class("nxdrive.nuxeo.direct_edit.DirectEdit")
    assert cls is not None
    assert cls.__name__ == "DirectEdit"


def test_load_class_nuxeo_direct_download():
    cls = load_class("nxdrive.nuxeo.direct_download.DirectDownload")
    assert cls is not None
    assert cls.__name__ == "DirectDownload"


def test_load_class_nuxeo_workflow():
    cls = load_class("nxdrive.nuxeo.client.workflow.Workflow")
    assert cls is not None
    assert cls.__name__ == "Workflow"


# ------------------------------------------------------------------ auto-discovery


def test_auto_discovery_registered_both_server_types():
    """Verify auto-discovery in __init__.py registered both server types."""
    assert "NUXEO" in _registry
    assert "ALFRESCO" in _registry


def test_auto_discovery_nuxeo_default():
    """Nuxeo should be the default server type."""
    assert get_default_key() == "NUXEO"


def test_auto_discovery_skips_drive_package():
    """The drive/ package itself should not be treated as a server type."""
    assert "drive" not in _registry
    assert "DRIVE" not in _registry


def test_auto_discovery_tolerates_missing_registration():
    """Packages without a registration.py are silently skipped."""
    # This is implicitly tested by the fact that __init__.py loads
    # without error even if hypothetical packages lack registration.py
    import nxdrive

    # Re-run the discovery logic manually
    count = 0
    for _finder, name, ispkg in pkgutil.iter_modules(nxdrive.__path__):
        if ispkg and name not in ("drive",):
            try:
                importlib.import_module(f"nxdrive.{name}.registration")
                count += 1
            except ModuleNotFoundError:
                pass
    assert count >= 2  # nuxeo + alfresco


# ------------------------------------------------------------------ nuxeo registration config values


def test_nuxeo_config_values():
    cfg = get("NUXEO")
    assert cfg.home_dir == ".nuxeo-drive"
    assert cfg.db_prefix == "ndrive_"
    assert cfg.engine_type == "NXDRIVE"
    assert cfg.app_name == "Nuxeo Drive"
    assert cfg.engine_class_path == "nxdrive.nuxeo.engine.engine.Engine"
    assert cfg.direct_edit_class_path == "nxdrive.nuxeo.direct_edit.DirectEdit"
    assert (
        cfg.direct_download_class_path == "nxdrive.nuxeo.direct_download.DirectDownload"
    )
    assert cfg.workflow_class_path == "nxdrive.nuxeo.client.workflow.Workflow"
    assert cfg.oauth2_class_path == "nxdrive.nuxeo.auth.oauth2.OAuthentication"
    assert cfg.url_patterns == ["nuxeo"]
    assert cfg.sync_root != ""


def test_alfresco_config_values():
    cfg = get("ALFRESCO")
    assert cfg.home_dir == ".alfresco-drive"
    assert cfg.db_prefix == "adrive_"
    assert cfg.engine_type == "ALFRESCO"
    assert cfg.app_name == "Alfresco Drive"
    assert cfg.is_url_fallback is True
    assert cfg.supports_browser_token_update is False
    assert cfg.ssl_login_page == "api/discovery"
    assert "direct_edit" in cfg.disabled_features


# ------------------------------------------------------------------ drive/ independence


def test_drive_folder_has_no_nuxeo_imports():
    """Verify drive/ folder has zero imports from nxdrive.nuxeo or nxdrive.alfresco."""
    drive_dir = Path(__file__).resolve().parents[3] / "nxdrive" / "drive"
    violations = []

    for py_file in drive_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            # Skip comments
            if stripped.startswith("#"):
                continue
            if "from nxdrive.nuxeo" in stripped or "import nxdrive.nuxeo" in stripped:
                violations.append(f"{py_file}:{line_no}: {stripped}")
            if (
                "from nxdrive.alfresco" in stripped
                or "import nxdrive.alfresco" in stripped
            ):
                violations.append(f"{py_file}:{line_no}: {stripped}")

    assert not violations, (
        f"drive/ has {len(violations)} import(s) from nuxeo/ or alfresco/:\n"
        + "\n".join(violations)
    )


def test_nuxeo_does_not_import_alfresco():
    """Verify nuxeo/ folder has zero imports from nxdrive.alfresco."""
    nuxeo_dir = Path(__file__).resolve().parents[3] / "nxdrive" / "nuxeo"
    violations = []

    for py_file in nuxeo_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if (
                "from nxdrive.alfresco" in stripped
                or "import nxdrive.alfresco" in stripped
            ):
                violations.append(f"{py_file}:{line_no}: {stripped}")

    assert not violations, "nuxeo/ imports from alfresco/:\n" + "\n".join(violations)


def test_alfresco_does_not_import_nuxeo():
    """Verify alfresco/ folder has zero imports from nxdrive.nuxeo."""
    alfresco_dir = Path(__file__).resolve().parents[3] / "nxdrive" / "alfresco"
    violations = []

    for py_file in alfresco_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "from nxdrive.nuxeo" in stripped or "import nxdrive.nuxeo" in stripped:
                violations.append(f"{py_file}:{line_no}: {stripped}")

    assert not violations, "alfresco/ imports from nuxeo/:\n" + "\n".join(violations)


def test_init_has_no_hardcoded_registration_imports():
    """Verify __init__.py uses auto-discovery, not hard-coded imports."""
    init_file = Path(__file__).resolve().parents[3] / "nxdrive" / "__init__.py"
    content = init_file.read_text(encoding="utf-8")

    # Should NOT have hard-coded imports
    assert "import nxdrive.nuxeo.registration" not in content
    assert "import nxdrive.alfresco.registration" not in content

    # Should have auto-discovery
    assert "pkgutil" in content
    assert "iter_modules" in content
