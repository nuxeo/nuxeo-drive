# coding: utf-8
from unittest.mock import patch
from pathlib import Path

import pytest

from nxdrive.client.proxy import (
    AutomaticProxy,
    ManualProxy,
    get_proxy,
    load_proxy,
    save_proxy,
)
from nxdrive.constants import MAC, WINDOWS
from nxdrive.engine.dao.sqlite import ConfigurationDAO
from nxdrive.manager import Manager
from nxdrive.options import Options

js = """
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
def pac_file():
    pac = Path("proxy.pac")
    pac.write_text(js)

    yield pac.resolve().as_uri()

    try:
        pac.unlink()
    except:
        pass


def test_manual_proxy():
    proxy = get_proxy(category="Manual", url="localhost:3128")
    assert isinstance(proxy, ManualProxy)
    settings = proxy.settings()
    assert settings["http"] == settings["https"] == proxy.url == "http://localhost:3128"


def test_pac_proxy_js():
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


@pytest.mark.skipif(not WINDOWS, reason="Only for Windows")
def test_mock_autoconfigurl_windows(pac_file):
    with _patch_winreg_qve(return_value=(pac_file, "foo")):
        proxy = get_proxy(category="Automatic")
        assert isinstance(proxy, AutomaticProxy)
        assert proxy._pac_file
        settings = proxy.settings("http://nuxeo.com")
        assert settings["http"] == settings["https"] == "http://localhost:8899"
        settings = proxy.settings("http://example.com")
        assert settings["http"] is None
        assert settings["https"] is None


def _patch_pyobjc_dscp(**kwargs):
    return patch(
        "pypac.os_settings.SystemConfiguration.SCDynamicStoreCopyProxies", **kwargs
    )


@pytest.mark.skipif(not MAC, reason="Only for macOS")
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
def test_cli_args():
    url = "http://username:password@localhost:8899"
    Options.set("proxy_server", url, setter="cli")
    manager = Manager()
    proxy = manager.proxy
    assert isinstance(proxy, ManualProxy)
    assert proxy.url == url
    settings = proxy.settings()
    assert settings["http"] == settings["https"] == url
    manager.stop()
    manager.unbind_all()
    manager.dispose_all()
    Manager._singleton = None
