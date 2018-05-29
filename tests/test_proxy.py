# coding: utf-8
import os

import pytest

from nxdrive.client.proxy import *
from nxdrive.engine.dao.sqlite import ConfigurationDAO


@pytest.fixture()
def config_dao():
    dao = ConfigurationDAO('tmp.db')
    yield dao
    dao.dispose()
    os.remove('tmp.db')


def test_manual_proxy():
    proxy = get_proxy(category='Manual', url='localhost:3128')
    assert isinstance(proxy, ManualProxy)
    assert not proxy.authenticated
    assert proxy.scheme == 'http'
    assert proxy.host == 'localhost'
    assert proxy.port == 3128
    settings = proxy.settings()
    assert settings['http'] == settings['https'] == 'http://localhost:3128'


def test_pac_proxy():
    js = '''
        function FindProxyForURL(url, host) {
            if (shExpMatch(host, "nuxeo.com"))
            {
                return "PROXY localhost:8899";
            }
            return "DIRECT";
        }
    '''
    proxy = get_proxy(category='Automatic', js=js)
    assert isinstance(proxy, AutomaticProxy)
    settings = proxy.settings('http://nuxeo.com')
    assert settings['http'] == settings['https'] == 'http://localhost:8899'
    settings = proxy.settings('http://example.com')
    assert settings['http'] is None
    assert settings['https'] is None


def test_load(config_dao):
    proxy = get_proxy(category='Manual', url='localhost:3128')

    save_proxy(proxy, config_dao, 'mock_token')
    loaded_proxy = load_proxy(config_dao, 'mock_token')

    assert isinstance(loaded_proxy, ManualProxy)
    assert loaded_proxy.authenticated == proxy.authenticated
    assert loaded_proxy.scheme == proxy.scheme
    assert loaded_proxy.host == proxy.host
    assert loaded_proxy.port == proxy.port
    assert proxy.settings() == loaded_proxy.settings()
