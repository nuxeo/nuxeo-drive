# coding: utf-8
from pathlib import Path
from unittest.mock import patch

import pytest

from nxdrive.client.proxy import (
    AutomaticProxy,
    ManualProxy,
    get_proxy,
    load_proxy,
    save_proxy,
)
from nxdrive.constants import WINDOWS
from nxdrive.engine.dao.sqlite import ConfigurationDAO
from nxdrive.manager import Manager
from nxdrive.options import Options

from ..markers import mac_only, windows_only


@pytest.fixture(scope="module")
def js():
    return """
    function FindProxyForURL(url, host) {
        if (shExpMatch(host, "nuxeo.com"))
        {
            return "PROXY localhost:8899";
        }
        return "DIRECT";
    }
    """


@pytest.fixture()
def config_dao():
    db = Path("tmp.db")
    dao = ConfigurationDAO(db)
    yield dao
    dao.dispose()
    db.unlink()


@pytest.fixture()
def pac_file(tmp_path, js):
    pac = tmp_path / "proxy.pac"
    pac.write_text(js, encoding="utf-8")

    uri = pac.resolve().as_uri()
    if WINDOWS:
        uri = uri.replace("///", "//")

    yield uri

    pac.unlink()


def test_manual_proxy():
    proxy = get_proxy(category="Manual", url="localhost:3128")
    assert isinstance(proxy, ManualProxy)
    settings = proxy.settings()
    assert settings["http"] == settings["https"] == proxy.url == "http://localhost:3128"


def test_pac_proxy_js(js):
    proxy = get_proxy(category="Automatic", js=js)
    assert isinstance(proxy, AutomaticProxy)
    settings = proxy.settings("http://nuxeo.com")
    assert settings["http"] == settings["https"] == "http://localhost:8899"
    settings = proxy.settings("http://example.com")
    assert settings["http"] is None
    assert settings["https"] is None


def test_load(config_dao):
    proxy = get_proxy(category="Manual", url="localhost:3128")

    save_proxy(proxy, config_dao, "mock_token")
    loaded_proxy = load_proxy(config_dao, "mock_token")

    assert isinstance(loaded_proxy, ManualProxy)
    assert proxy.settings() == loaded_proxy.settings()


def _patch_winreg_qve(**kwargs):
    return patch("pypac.os_settings.winreg.QueryValueEx", **kwargs)


@windows_only
def test_mock_autoconfigurl_windows(pac_file):
    with _patch_winreg_qve(return_value=(pac_file, "foo")):
        proxy = get_proxy(category="Automatic")
        assert isinstance(proxy, AutomaticProxy)
        assert proxy._pac_file is not None
        settings = proxy.settings("http://nuxeo.com")
        assert settings["http"] == settings["https"] == "http://localhost:8899"
        settings = proxy.settings("http://example.com")
        assert settings["http"] is None
        assert settings["https"] is None


def _patch_pyobjc_dscp(**kwargs):
    return patch(
        "pypac.os_settings.SystemConfiguration.SCDynamicStoreCopyProxies", **kwargs
    )


@mac_only
def test_mock_autoconfigurl_mac(pac_file):
    with _patch_pyobjc_dscp(
        return_value={"ProxyAutoConfigEnable": 1, "ProxyAutoConfigURLString": pac_file}
    ):
        proxy = get_proxy(category="Automatic")
        assert isinstance(proxy, AutomaticProxy)
        assert proxy._pac_file
        settings = proxy.settings("http://nuxeo.com")
        assert settings["http"] == settings["https"] == "http://localhost:8899"
        settings = proxy.settings("http://example.com")
        assert settings["http"] is None
        assert settings["https"] is None


@Options.mock()
def test_cli_args(tmp):
    url = "http://username:password@localhost:8899"
    Options.set("proxy_server", url, setter="cli")
    with Manager(tmp()) as manager:
        proxy = manager.proxy
        assert isinstance(proxy, ManualProxy)
        assert proxy.url == url
        settings = proxy.settings()
        assert settings["http"] == settings["https"] == url
