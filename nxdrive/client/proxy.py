# coding: utf-8
from logging import getLogger
from urlparse import urlparse

import requests
from pypac import get_pac
from pypac.resolver import ProxyResolver

from nxdrive.utils import decrypt, encrypt

log = getLogger(__name__)


class MissingToken(Exception):
    pass


class Proxy(object):
    _type = None

    def __init__(self, **kwargs):
        pass


class NoProxy(Proxy):
    _type = 'None'

    def settings(self, **kwargs):
        # type: (Any) -> Dict[Text, Any]
        return {'http': None, 'https': None}

    def __repr__(self):
        # type: () -> Text
        return 'NoProxy< >'


class SystemProxy(Proxy):
    _type = 'System'

    def settings(self, **kwargs):
        # type: (Any) -> None
        return None

    def __repr__(self):
        # type: () -> Text
        return 'SystemProxy< >'


class ManualProxy(Proxy):
    _type = 'Manual'

    def __init__(
        self,
        url=None,  # type: Optional[Text]
        scheme=None,  # type: Optional[Text]
        host=None,  # type: Optional[Text]
        port=None,  # type: Optional[int]
        authenticated=False,  # type: bool
        username=None,  # type: Optional[Text]
        password=None,  # type: Optional[Text]
        **kwargs  # type: Any
    ):
        # type: (...) -> None
        super(ManualProxy, self).__init__(**kwargs)
        if url:
            if '://' not in url:
                url = 'http://' + url
            url = urlparse(url)
            self.scheme = url.scheme
            self.host = url.hostname
            self.port = url.port
        else:
            self.scheme = scheme
            self.host = host
            self.port = port

        self.authenticated = authenticated
        self.username = username
        self.password = password

    @property
    def url(self):
        if self.authenticated:
            return (self.scheme + '://' + self.username + ':'
                    + self.password + '@' + str(self.host))
        else:
            return self.scheme + '://' + self.host + ':' + str(self.port)

    def settings(self, **kwargs):
        # type: (Any) -> Dict[Text, Any]
        return {'http': self.url, 'https': self.url}

    def __repr__(self):
        # type: () -> Text
        return ('ManualProxy<scheme=%r, host=%r, port=%r, authenticated=%r, '
                'username=%r>') % (self.scheme, self.host, self.port,
                                   self.authenticated, self.username)


class AutomaticProxy(Proxy):
    _type = 'Automatic'

    def __init__(self, pac_url=None, js=None, **kwargs):
        # type: (Optional[Text], Optional[Text], Any) -> None
        super(AutomaticProxy, self).__init__(**kwargs)
        self.pac_url = pac_url
        self.js = js
        self.pac_file = get_pac(url=pac_url, js=js)
        self.resolver = ProxyResolver(self.pac_file)

    def settings(self, url=None, **kwargs):
        # type: (Optional[Text], Any) -> Dict[Text, Any]
        return self.resolver.get_proxy_for_requests(url)

    def __repr__(self):
        # type: () -> Text
        return 'AutomaticProxy<pac_url=%r>' % self.pac_url


def get_proxy(**kwargs):
    # type: (Any) -> Type[Proxy]
    return _get_cls(kwargs.pop('_type'))(**kwargs)


def load_proxy(dao, token=None):
    # type: (ConfigurationDAO, Optional[Text]) -> Type[Proxy]
    _type = dao.get_config('proxy_config', 'System')
    kwargs = {}

    if _type == 'Automatic':
        kwargs['pac_url'] = dao.get_config('proxy_pac_url')

    elif _type == 'Manual':
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

    return _get_cls(_type)(**kwargs)


def save_proxy(proxy, dao, token=None):
    # type: (Type[Proxy], ConfigurationDAO, Optional[Text]) -> None
    dao.update_config('proxy_config', proxy._type)

    if proxy._type == 'Automatic':
        dao.update_config('proxy_pac_url', proxy.pac_url)

    elif proxy._type == 'Manual':
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


def validate_proxy(proxy, url):
    # type: (Type[Proxy], Text) -> bool
    try:
        requests.get(url, proxies=proxy.settings(url=url))
        return True
    except Exception as e:
        log.exception('Invalid proxy.')
        return False


def _get_cls(_type):
    # type: (Text) -> Type[Proxy]
    proxy_cls = {
        'None': NoProxy,
        'System': SystemProxy,
        'Manual': ManualProxy,
        'Automatic': AutomaticProxy
    }
    if _type not in proxy_cls:
        raise ValueError('No proxy associated to type %s' % _type)
    return proxy_cls[_type]
