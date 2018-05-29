# coding: utf-8
from logging import getLogger
from urlparse import urlparse

import requests
from pypac import get_pac
from pypac.resolver import ProxyResolver

from ..utils import decrypt, encrypt

log = getLogger(__name__)


class MissingToken(Exception):
    pass


class Proxy(object):
    category = None

    def __init__(self, **kwargs):
        """
        Empty init so any subclass of Proxy can receive any kwargs
        and not raise an error.
        """
        pass

    def __repr__(self):
        # type: (None) -> Text
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

    def settings(self, **kwargs):
        # type: (Any) -> Dict[Text, Any]
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

    def settings(self, **kwargs):
        # type: (Any) -> None
        return None


class ManualProxy(Proxy):
    """
    The ManualProxy class allows for manual setting of the proxy.
    """
    category = 'Manual'

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
        return self.scheme + '://' + self.host + ':' + str(self.port)

    def settings(self, **kwargs):
        # type: (Any) -> Dict[Text, Any]
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

    If the pac_url and the js arguments are both missing, and if the
    OS is Windows, then pypac will automatically try to retrieve the
    default PAC file address in the registry.
    """
    category = 'Automatic'

    def __init__(self, pac_url=None, js=None, **kwargs):
        # type: (Optional[Text], Optional[Text], Any) -> None
        super(AutomaticProxy, self).__init__(**kwargs)
        if '://' not in pac_url:
            pac_url = 'http://' + pac_url
        self.pac_url = pac_url
        self._js = js
        self._pac_file = get_pac(
            url=pac_url, js=js,
            allowed_content_types='application/octet-stream')
        self._resolver = ProxyResolver(self._pac_file)

    def settings(self, url=None, **kwargs):
        # type: (Optional[Text], Any) -> Dict[Text, Any]
        return self._resolver.get_proxy_for_requests(url)


def get_proxy(**kwargs):
    # type: (Any) -> Type[Proxy]
    return _get_cls(kwargs.pop('category'))(**kwargs)


def load_proxy(dao, token=None):
    # type: (ConfigurationDAO, Optional[Text]) -> Type[Proxy]
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
                password = decrypt(password, str(token))
            else:
                # If no server binding or no token available
                # (possibly after token revocation) reset password
                password = ''
            kwargs['password'] = password

    return _get_cls(category)(**kwargs)


def save_proxy(proxy, dao, token=None):
    # type: (Type[Proxy], ConfigurationDAO, Optional[Text]) -> None
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
            password = encrypt(proxy.password, str(token))
            dao.update_config('proxy_password', password)



def validate_proxy(proxy, url):
    # type: (Type[Proxy], Text) -> bool
    try:
        requests.get(url, proxies=proxy.settings(url=url))
        return True
    except:
        log.exception('Invalid proxy.')
        return False


def _get_cls(category):
    # type: (Text) -> Type[Proxy]
    proxy_cls = {
        'None': NoProxy,
        'System': SystemProxy,
        'Manual': ManualProxy,
        'Automatic': AutomaticProxy,
    }
    if category not in proxy_cls:
        raise ValueError('No proxy associated to category %s' % category)
    return proxy_cls[category]
