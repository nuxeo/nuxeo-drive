from logging import getLogger
from typing import TYPE_CHECKING, Any, Dict, Type

import requests
from pypac import get_pac
from pypac.resolver import ProxyResolver

from ..metrics.utils import user_agent
from ..options import Options
from ..utils import client_certificate, decrypt, encrypt, force_decode

if TYPE_CHECKING:
    from ..dao.engine import EngineDAO  # noqa

__all__ = (
    "AutomaticProxy",
    "ManualProxy",
    "Proxy",
    "get_proxy",
    "load_proxy",
    "save_proxy",
    "validate_proxy",
)

log = getLogger(__name__)


class Proxy:
    category: str

    def __init__(self, *, url: str = "", pac_url: str = "") -> None:
        """
        Empty init so any subclass of Proxy can receive those kwargs
        and not raise an error.
        """
        pass

    def __repr__(self) -> str:
        attrs = ", ".join(
            f"{attr}={getattr(self, attr, None)!r}"
            for attr in sorted(vars(self))
            if not attr.startswith("_")
        )
        return f"{type(self).__name__}<{attrs}>"

    def settings(self, *, url: str = None) -> Dict[str, Any]:
        return {}


class NoProxy(Proxy):
    """
    The NoProxy class forces to bypass the system proxy settings.

    By returning non-null settings, we overwrite the default proxy
    used by the requests module. But since the proxy address is None,
    requests is not going to use any proxy to perform the request.
    """

    category = "None"

    def settings(self, *, url: str = None) -> Dict[str, Any]:
        return {"http": None, "https": None}


class SystemProxy(Proxy):
    """
    The SystemProxy class allows the usage of the system proxy settings.

    It is the default proxy setting in Nuxeo Drive.
    Its settings() method return None, which means that it won't overwrite
    the proxy used by the requests module. The requests module thus uses
    the system proxy configuration by default.
    """

    category = "System"


class ManualProxy(Proxy):
    """
    The ManualProxy class allows for manual setting of the proxy.
    """

    category = "Manual"

    def __init__(self, *, url: str = "", pac_url: str = "") -> None:
        if "://" not in url:
            url = f"http://{url}"
        self.url = url

    def settings(self, *, url: str = None) -> Dict[str, Any]:
        return {"http": self.url, "https": self.url}


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

    category = "Automatic"

    def __init__(self, *, url: str = "", pac_url: str = "") -> None:
        args: Dict[str, Any] = {}

        if pac_url:
            # Load the PAC file as PyPAC won't do it for us
            if pac_url.startswith("file:"):
                with open(pac_url.replace("file://", "")) as pac:
                    args["js"] = pac.read()
            else:
                args["url"] = pac_url
                args["allowed_content_types"] = [
                    "application/octet-stream",
                    "application/x-ns-proxy-autoconfig",
                    "application/x-javascript-config",
                ]

        self.pac_url = pac_url
        self._pac_file = get_pac(**args)
        self._resolver = ProxyResolver(self._pac_file)

    def settings(self, *, url: str = None) -> Dict[str, Any]:
        ret: Dict[str, Any] = self._resolver.get_proxy_for_requests(url)
        return ret


def get_proxy(category: str, /, *, url: str = "", pac_url: str = "") -> Proxy:
    log.debug(f"Get proxy with {url = } and {pac_url = }")
    proxy = _get_cls(category)(url=url, pac_url=pac_url)
    log.debug(f"Got {proxy = }")
    return proxy


def load_proxy(dao: "EngineDAO", *, token: str = "") -> Proxy:
    category = dao.get_config("proxy_config", default="System")
    kwargs = {}

    if category == "Automatic":
        kwargs["pac_url"] = dao.get_config("proxy_pac_url")
    elif category == "Manual":
        if not token:
            token = dao.get_config("device_id")
        token += "_proxy"

        url = dao.get_config("proxy_url")
        if url:
            # This is the new proxy settings
            kwargs["url"] = force_decode(decrypt(url, token) or "")
        else:
            # We need to convert the old settings to the new format
            url = (dao.get_config("proxy_type") or "http") + "://"
            username = dao.get_config("proxy_username")
            password = dao.get_config("proxy_password")
            if username and password:
                password = decrypt(password, token)
                url += f"{username}:{force_decode(password)}@"
            url += dao.get_config("proxy_server")
            port = dao.get_config("proxy_port")
            if port:
                url += f":{port}"

            kwargs["url"] = url

    return _get_cls(category)(**kwargs)


def save_proxy(proxy: Proxy, dao: "EngineDAO", *, token: str = None) -> None:
    dao.update_config("proxy_config", proxy.category)

    if isinstance(proxy, AutomaticProxy):
        dao.update_config("proxy_pac_url", proxy.pac_url)
    elif isinstance(proxy, ManualProxy):
        # Encrypt password with token as the secret
        token = (token or dao.get_config("device_id")) + "_proxy"
        dao.update_config("proxy_url", encrypt(proxy.url, token))


def validate_proxy(proxy: Proxy, url: str, /) -> bool:
    verify = Options.ca_bundle or not Options.ssl_no_verify
    headers = {"User-Agent": user_agent()}
    try:
        with requests.get(
            url,
            headers=headers,
            proxies=proxy.settings(url=url),
            verify=verify,
            cert=client_certificate(),
        ):
            return True
    except OSError:
        # OSError: Could not find a suitable TLS CA certificate bundle, invalid path: ...
        log.warning("Ensure the 'ca_bundle' option is correct.", exc_info=True)
    except AttributeError:
        log.warning(
            "Invalid PAC URL or invalid data retrieved from the PAC URL.", exc_info=True
        )
    except Exception:
        log.exception("Invalid proxy.")
    return False


def _get_cls(category: str, /) -> Type[Proxy]:
    proxy_cls = {
        "None": NoProxy,
        "System": SystemProxy,
        "Manual": ManualProxy,
        "Automatic": AutomaticProxy,
    }
    if category not in proxy_cls:
        raise ValueError(f"No proxy associated to category {category}")
    return proxy_cls[category]
