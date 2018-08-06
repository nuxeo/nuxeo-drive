# coding: utf-8
import os

import pytest
from unittest.mock import patch

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
    dao = ConfigurationDAO("tmp.db")
    yield dao
    dao.dispose()
    os.remove("tmp.db")


@pytest.fixture()
def pac_file():
    pac = "proxy.pac"
    with open(pac, "w") as f:
        f.write(js)

    path = "file://" + os.path.abspath(pac)
    if WINDOWS:
        # PyPAC does not accept "file://E:\\proxy.pac" but "file://E:/proxy.pac"
        path = path.replace("\\", "/")

    yield path

    try:
        os.remove(pac)
    except:
        pass


def test_manual_proxy():
    proxy = get_proxy(category="Manual", url="localhost:3128")
    assert isinstance(proxy, ManualProxy)
    assert not proxy.authenticated
    assert proxy.scheme == "http"
    assert proxy.host == "localhost"
    assert proxy.port == 3128
    settings = proxy.settings()
    assert settings["http"] == settings["https"] == "http://localhost:3128"


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
    assert loaded_proxy.authenticated == proxy.authenticated
    assert loaded_proxy.scheme == proxy.scheme
    assert loaded_proxy.host == proxy.host
    assert loaded_proxy.port == proxy.port
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
    assert proxy
    assert isinstance(proxy, ManualProxy)
    assert proxy.authenticated
    assert proxy.scheme == "http"
    assert proxy.host == "localhost"
    assert proxy.port == 8899
    assert proxy.username == "username"
    assert proxy.password == "password"
    settings = proxy.settings()
    assert settings["http"] == settings["https"] == url
    manager.stop()
    manager.unbind_all()
    manager.dispose_all()
    Manager._singleton = None
