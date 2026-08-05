import importlib
import importlib.util
import pkgutil
import sys
from pathlib import Path
from unittest.mock import call, patch

import pytest

import nxdrive

INIT_PATH = Path(__file__).parents[3] / "nxdrive" / "__init__.py"


def _init_module(monkeypatch, name):
    spec = importlib.util.spec_from_file_location(
        name,
        INIT_PATH,
        submodule_search_locations=[str(INIT_PATH.parent)],
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    return spec, module


def test_package_import_discovers_registrations_and_skips_missing(monkeypatch):
    spec, module = _init_module(monkeypatch, "nxdrive._tested_init_discovery")
    modules = [
        (None, "missing", True),
        (None, "server", True),
        (None, "drive", True),
        (None, "plain_module", False),
    ]

    def import_registration(name):
        if name == "nxdrive.missing.registration":
            raise ModuleNotFoundError(name)
        return object()

    with patch.object(sys, "frozen", False, create=True), patch.object(
        pkgutil, "iter_modules", return_value=modules
    ), patch.object(
        importlib, "import_module", side_effect=import_registration
    ) as import_module:
        spec.loader.exec_module(module)

    assert module._discovered == {"server"}
    assert import_module.call_args_list == [
        call("nxdrive.missing.registration"),
        call("nxdrive.server.registration"),
    ]


def test_frozen_package_import_uses_supported_server_fallback(monkeypatch, tmp_path):
    spec, module = _init_module(monkeypatch, "nxdrive._tested_init_frozen")
    (tmp_path / "supported_server_list.txt").write_text("GENERIC\n", encoding="utf-8")
    module.__file__ = str(tmp_path / "__init__.py")

    with patch.object(sys, "frozen", True, create=True), patch.object(
        pkgutil, "iter_modules"
    ) as iter_modules, patch.object(
        importlib, "import_module", side_effect=ModuleNotFoundError
    ) as import_module:
        spec.loader.exec_module(module)

    iter_modules.assert_not_called()
    import_module.assert_called_once_with("nxdrive.generic.registration")


def test_supported_packages_reads_configured_server_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(nxdrive, "__file__", str(tmp_path / "__init__.py"))
    (tmp_path / "supported_server_list.txt").write_text(
        "\n# enabled servers\n NUXEO \nAlFrEsCo\n",
        encoding="utf-8",
    )

    assert nxdrive._supported_packages() == ("nuxeo", "alfresco")


def test_supported_packages_discovers_valid_package_directories(monkeypatch, tmp_path):
    monkeypatch.setattr(nxdrive, "__file__", str(tmp_path / "__init__.py"))
    (tmp_path / "supported_server_list.txt").write_text(
        "# no configured servers\n", encoding="utf-8"
    )

    for name in ("zeta", "alpha", "drive"):
        package = tmp_path / name
        package.mkdir()
        (package / "__init__.py").touch()
        (package / "registration.py").touch()

    missing_init = tmp_path / "missing_init"
    missing_init.mkdir()
    (missing_init / "registration.py").touch()
    missing_registration = tmp_path / "missing_registration"
    missing_registration.mkdir()
    (missing_registration / "__init__.py").touch()
    (tmp_path / "plain_file").touch()

    assert nxdrive._supported_packages() == ("alpha", "zeta")


def test_supported_packages_suppresses_filesystem_errors(monkeypatch, tmp_path):
    missing_root = tmp_path / "missing"
    monkeypatch.setattr(nxdrive, "__file__", str(missing_root / "__init__.py"))

    assert nxdrive._supported_packages() == ()


@pytest.mark.parametrize(
    "name, module_name",
    [
        ("utils", "nxdrive.drive.utils"),
        ("autolocker", "nxdrive.drive.autolocker"),
        ("fatal_error", "nxdrive.drive.fatal_error"),
    ],
)
def test_legacy_module_attributes(name, module_name):
    assert nxdrive.__getattr__(name) is importlib.import_module(module_name)


def test_unknown_legacy_attribute_raises():
    with pytest.raises(AttributeError, match="has no attribute 'missing'"):
        nxdrive.__getattr__("missing")
