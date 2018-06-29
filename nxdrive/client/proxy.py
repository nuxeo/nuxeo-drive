# coding: utf-8
from logging import getLogger
from typing import Any, Dict
from urllib.parse import urlparse

import requests
from pypac import get_pac
from pypac.resolver import ProxyResolver

from ..utils import decrypt, encrypt

__all__ = ('AutomaticProxy', 'ManualProxy', 'Proxy', 'get_proxy', 'load_proxy',
           'save_proxy', 'validate_proxy')

log = getLogger(__name__)


class MissingToken(Exception):
    pass


class Proxy:
    category = None

    def __init__(self, **kwargs):
        """
        Empty init so any subclass of Proxy can receive any kwargs
        and not raise an error.
        """
        pass

    def __repr__(self):
        attrs = ', '.join('{}={!r}'.format(attr, getattr(self, attr, None))
                          for attr in sorted(vars(self))
                          if not attr.startswith('_'))
        return '{}<{}>'.format(type(self).__name__, attrs)


class NoProxy(Proxy):
    """
    The NoProxy class forces to bypass the system proxy settings.

    By returning non-null settings, we overwrite the default proxy
    used by the requests module. But since the proxy address is None,
    requests is not going to use any proxy to perform the request.
    """
    category = 'None'

    def settings(self, **kwargs: Any) -> Dict[str, Any]:
        return {'http': None, 'https': None}


class SystemProxy(Proxy):
    """
    The SystemProxy class allows the usage of the system proxy settings.

    It is the default proxy setting in Nuxeo Drive.
    Its settings() method return None, which means that it won't overwrite
    the proxy used by the requests module. The requests module thus uses
    the system proxy configuration by default.
    """
    category = 'System'

    def settings(self, **kwargs: Any) -> None:
        return None


class ManualProxy(Proxy):
    """
    The ManualProxy class allows for manual setting of the proxy.
    """
    category = 'Manual'

    def __init__(
        self,
        url: str=None,
        scheme: str=None,
        host: str=None,
        port: int=None,
        authenticated: bool=False,
        username: str=None,
        password: str=None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if url:
            if '://' not in url:
                url = 'http://' + url
            url = urlparse(url)
            self.scheme = url.scheme
            self.host = url.hostname
            self.port = url.port
            self.username = url.username
            self.password = url.password
            self.authenticated = bool(url.username)
        else:
            self.scheme = scheme
            self.host = host
            self.port = port
            self.username = username
            self.password = password
            self.authenticated = authenticated

    @property
    def url(self):
        return self.scheme + '://' + self.host + ':' + str(self.port)

    def settings(self, **kwargs: Any) -> Dict[str, Any]:
        if self.authenticated:
            url = (self.scheme + '://' + self.username + ':'
                   + self.password + '@' + self.host + ':' + str(self.port))
        else:
            url = self.url
        return {'http': url, 'https': url}


class AutomaticProxy(Proxy):
    """
    The AutomaticProxy relies on proxy auto-config files (or PAC files).

    The PAC file can be retrieved from a web address, or its JavaScript
    content can be directly passed to the constructor.

    If the pac_url and the js arguments are both missing:
       - macOS: pypac will automatically try to retrieve
                the default PAC file address in the system preferences
       - Windows: pypac will automatically try to retrieve
                  the default PAC file address in the registry
    """
    category = 'Automatic'

    def __init__(self, pac_url: str=None, js: str=None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if pac_url and '://' not in pac_url:
            pac_url = 'http://' + pac_url
        self.pac_url = pac_url
        self._js = js
        self._pac_file = get_pac(
            url=pac_url, js=js, allowed_content_types=[
                'application/octet-stream',
                'application/x-ns-proxy-autoconfig',
                'application/x-javascript-config'])
        self._resolver = ProxyResolver(self._pac_file)

    def settings(self, url: str=None, **kwargs: Any) -> Dict[str, Any]:
        return self._resolver.get_proxy_for_requests(url)


def get_proxy(**kwargs: Any) -> Proxy:
    return _get_cls(kwargs.pop('category'))(**kwargs)


def load_proxy(dao: object, token: str=None) -> Proxy:
    category = dao.get_config('proxy_config', 'System')
    kwargs = {}

    if category == 'Automatic':
        kwargs['pac_url'] = dao.get_config('proxy_pac_url')

    elif category == 'Manual':
        kwargs['scheme'] = dao.get_config('proxy_type')
        kwargs['port'] = int(dao.get_config('proxy_port'))
        kwargs['host'] = dao.get_config('proxy_server')
        kwargs['authenticated'] = (dao.get_config('proxy_authenticated', '0') == '1')
        if kwargs['authenticated']:
            kwargs['username'] = dao.get_config('proxy_username')
            password = dao.get_config('proxy_password')
            if token is None:
                token = dao.get_config('device_id')
            if password is not None and token is not None:
                token += '_proxy'
                password = decrypt(password, token)
            else:
                # If no server binding or no token available
                # (possibly after token revocation) reset password
                password = ''
            kwargs['password'] = password

    return _get_cls(category)(**kwargs)


def save_proxy(proxy: Proxy, dao: object, token: str=None) -> None:
    dao.update_config('proxy_config', proxy.category)

    if proxy.category == 'Automatic':
        dao.update_config('proxy_pac_url', proxy.pac_url)

    elif proxy.category == 'Manual':
        dao.update_config('proxy_port', proxy.port)
        dao.update_config('proxy_type', proxy.scheme)
        dao.update_config('proxy_server', proxy.host)
        dao.update_config('proxy_authenticated', proxy.authenticated)

        if proxy.authenticated:
            dao.update_config('proxy_username', proxy.username)
            # Encrypt password with token as the secret
            if token is None:
                token = dao.get_config('device_id')
            if token is None:
                raise MissingToken(
                    'Your token has been revoked, please update '
                    'your password to acquire a new one.')
            token += '_proxy'
            password = encrypt(proxy.password, token)
            dao.update_config('proxy_password', password)


def validate_proxy(proxy: Proxy, url: str) -> bool:
    try:
        requests.get(url, proxies=proxy.settings(url=url))
        return True
    except:
        log.exception('Invalid proxy.')
        return False


def _get_cls(category: str) -> bool:
    proxy_cls = {
        'None': NoProxy,
        'System': SystemProxy,
        'Manual': ManualProxy,
        'Automatic': AutomaticProxy,
    }
    if category not in proxy_cls:
        raise ValueError('No proxy associated to category %s' % category)
    return proxy_cls[category]
