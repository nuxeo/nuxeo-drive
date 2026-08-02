"""Extra unit tests for nxdrive.drive.client.proxy — targets uncovered lines."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from nxdrive.drive.client.proxy import (
    AutomaticProxy,
    ManualProxy,
    NoProxy,
    Proxy,
    SystemProxy,
    _get_cls,
    get_proxy,
    load_proxy,
    save_proxy,
    validate_proxy,
)

# ------------------------------------------------------------------ Proxy base


class TestProxyRepr:
    def test_repr_empty(self):
        p = Proxy()
        # No instance vars set by default Proxy.__init__
        assert "Proxy<" in repr(p)

    def test_repr_with_attrs(self):
        p = Proxy()
        p.foo = "bar"
        r = repr(p)
        assert "foo='bar'" in r
        assert "Proxy<" in r

    def test_repr_skips_private(self):
        p = Proxy()
        p._secret = "hidden"
        p.visible = 1
        r = repr(p)
        assert "_secret" not in r
        assert "visible=1" in r


class TestProxySettings:
    def test_base_returns_empty_dict(self):
        assert Proxy().settings() == {}

    def test_base_settings_with_url_kwarg(self):
        assert Proxy().settings(url="http://example.com") == {}


# ------------------------------------------------------------------ NoProxy


class TestNoProxy:
    def test_category(self):
        assert NoProxy.category == "None"

    def test_settings_returns_none_proxies(self):
        s = NoProxy().settings()
        assert s == {"http": None, "https": None}

    def test_settings_with_url(self):
        s = NoProxy().settings(url="http://example.com")
        assert s == {"http": None, "https": None}


# ------------------------------------------------------------------ SystemProxy


class TestSystemProxy:
    def test_category(self):
        assert SystemProxy.category == "System"

    def test_settings_returns_empty(self):
        assert SystemProxy().settings() == {}


# ------------------------------------------------------------------ ManualProxy


class TestManualProxy:
    def test_url_with_scheme(self):
        p = ManualProxy(url="https://proxy.local:8080")
        assert p.url == "https://proxy.local:8080"

    def test_url_without_scheme_gets_http(self):
        p = ManualProxy(url="proxy.local:3128")
        assert p.url == "http://proxy.local:3128"

    def test_settings(self):
        p = ManualProxy(url="http://proxy.local:3128")
        s = p.settings()
        assert s["http"] == "http://proxy.local:3128"
        assert s["https"] == "http://proxy.local:3128"

    def test_settings_with_url(self):
        p = ManualProxy(url="http://proxy.local:3128")
        s = p.settings(url="http://target.com")
        assert s["http"] == "http://proxy.local:3128"

    def test_category(self):
        assert ManualProxy.category == "Manual"


# ------------------------------------------------------------------ AutomaticProxy


class TestAutomaticProxy:
    def test_no_pac_url_uses_system(self):
        mock_pac = MagicMock()
        with patch("nxdrive.drive.client.proxy.get_pac", return_value=mock_pac):
            with patch("nxdrive.drive.client.proxy.ProxyResolver"):
                p = AutomaticProxy()
        assert p.pac_url == ""
        assert p._pac_file is mock_pac

    def test_pac_url_http(self):
        mock_pac = MagicMock()
        with patch("nxdrive.drive.client.proxy.get_pac", return_value=mock_pac) as gp:
            with patch("nxdrive.drive.client.proxy.ProxyResolver"):
                p = AutomaticProxy(pac_url="http://proxy.local/proxy.pac")
        assert p.pac_url == "http://proxy.local/proxy.pac"
        call_kwargs = gp.call_args[1]
        assert call_kwargs["url"] == "http://proxy.local/proxy.pac"
        assert "allowed_content_types" in call_kwargs

    def test_pac_url_file(self):
        mock_pac = MagicMock()
        js_content = "function FindProxyForURL() { return 'DIRECT'; }"
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__ = Mock(
                return_value=Mock(read=Mock(return_value=js_content))
            )
            mock_open.return_value.__exit__ = Mock(return_value=False)
            with patch(
                "nxdrive.drive.client.proxy.get_pac", return_value=mock_pac
            ) as gp:
                with patch("nxdrive.drive.client.proxy.ProxyResolver"):
                    p = AutomaticProxy(pac_url="file:///tmp/proxy.pac")
        assert p.pac_url == "file:///tmp/proxy.pac"
        call_kwargs = gp.call_args[1]
        assert call_kwargs["js"] == js_content

    def test_settings_delegates_to_resolver(self):
        mock_pac = MagicMock()
        mock_resolver_inst = MagicMock()
        mock_resolver_inst.get_proxy_for_requests.return_value = {
            "http": "http://px:1234"
        }
        with patch("nxdrive.drive.client.proxy.get_pac", return_value=mock_pac):
            with patch(
                "nxdrive.drive.client.proxy.ProxyResolver",
                return_value=mock_resolver_inst,
            ):
                p = AutomaticProxy()
        result = p.settings(url="http://example.com")
        assert result == {"http": "http://px:1234"}
        mock_resolver_inst.get_proxy_for_requests.assert_called_once_with(
            "http://example.com"
        )

    def test_category(self):
        assert AutomaticProxy.category == "Automatic"


# ------------------------------------------------------------------ get_proxy


class TestGetProxy:
    def test_none(self):
        p = get_proxy("None")
        assert isinstance(p, NoProxy)

    def test_system(self):
        p = get_proxy("System")
        assert isinstance(p, SystemProxy)

    def test_manual(self):
        p = get_proxy("Manual", url="http://localhost:3128")
        assert isinstance(p, ManualProxy)
        assert p.url == "http://localhost:3128"

    def test_automatic(self):
        with patch("nxdrive.drive.client.proxy.get_pac", return_value=MagicMock()):
            with patch("nxdrive.drive.client.proxy.ProxyResolver"):
                p = get_proxy("Automatic", pac_url="http://proxy/pac")
        assert isinstance(p, AutomaticProxy)

    def test_invalid_category_raises(self):
        with pytest.raises(ValueError, match="No proxy associated"):
            get_proxy("InvalidCategory")


# ------------------------------------------------------------------ _get_cls


class TestGetCls:
    def test_none(self):
        assert _get_cls("None") is NoProxy

    def test_system(self):
        assert _get_cls("System") is SystemProxy

    def test_manual(self):
        assert _get_cls("Manual") is ManualProxy

    def test_automatic(self):
        assert _get_cls("Automatic") is AutomaticProxy

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="No proxy associated"):
            _get_cls("Socks5")


# ------------------------------------------------------------------ load_proxy


class TestLoadProxy:
    def test_load_system_default(self):
        dao = MagicMock()
        dao.get_config.side_effect = lambda key, **kw: {
            "proxy_config": kw.get("default", None),
        }.get(key, None)
        # get_config("proxy_config", default="System") -> "System"
        dao.get_config.return_value = None
        dao.get_config.side_effect = lambda key, **kw: (
            "System" if key == "proxy_config" else None
        )
        proxy = load_proxy(dao)
        assert isinstance(proxy, SystemProxy)

    def test_load_manual_new_format(self):
        """Load Manual proxy with encrypted url (new format)."""
        from nxdrive.drive.utils import encrypt

        token = "device123"
        secret = token + "_proxy"
        original_url = "http://user:pass@proxy.local:3128"
        encrypted = encrypt(original_url, secret)

        dao = MagicMock()

        def mock_get_config(key, **kwargs):
            configs = {
                "proxy_config": "Manual",
                "device_id": token,
                "proxy_url": encrypted,
            }
            if key in configs:
                return configs[key]
            return kwargs.get("default", None)

        dao.get_config.side_effect = mock_get_config
        proxy = load_proxy(dao, token=token)
        assert isinstance(proxy, ManualProxy)
        assert proxy.url == original_url

    def test_load_manual_old_format_conversion(self):
        """Load Manual proxy with old settings (type/server/port/user/pass)."""
        from nxdrive.drive.utils import encrypt

        token = "device456"
        secret = token + "_proxy"
        password_encrypted = encrypt("secret", secret)

        dao = MagicMock()

        def mock_get_config(key, **kwargs):
            configs = {
                "proxy_config": "Manual",
                "device_id": token,
                "proxy_url": None,  # No new-format url -> triggers old format
                "proxy_type": "https",
                "proxy_username": "admin",
                "proxy_password": password_encrypted,
                "proxy_server": "old-proxy.local",
                "proxy_port": "9090",
            }
            if key in configs:
                return configs[key]
            return kwargs.get("default", None)

        dao.get_config.side_effect = mock_get_config
        proxy = load_proxy(dao, token=token)
        assert isinstance(proxy, ManualProxy)
        assert "old-proxy.local" in proxy.url
        assert ":9090" in proxy.url
        assert "admin:" in proxy.url

    def test_load_manual_old_format_no_credentials(self):
        """Old format without username/password."""
        dao = MagicMock()

        def mock_get_config(key, **kwargs):
            configs = {
                "proxy_config": "Manual",
                "device_id": "dev1",
                "proxy_url": None,
                "proxy_type": None,  # defaults to http
                "proxy_username": None,
                "proxy_password": None,
                "proxy_server": "simple-proxy.local",
                "proxy_port": None,
            }
            if key in configs:
                return configs[key]
            return kwargs.get("default", None)

        dao.get_config.side_effect = mock_get_config
        proxy = load_proxy(dao)
        assert isinstance(proxy, ManualProxy)
        assert proxy.url == "http://simple-proxy.local"

    def test_load_automatic(self):
        dao = MagicMock()

        def mock_get_config(key, **kwargs):
            configs = {
                "proxy_config": "Automatic",
                "proxy_pac_url": "http://proxy.local/proxy.pac",
            }
            if key in configs:
                return configs[key]
            return kwargs.get("default", None)

        dao.get_config.side_effect = mock_get_config
        with patch("nxdrive.drive.client.proxy.get_pac", return_value=MagicMock()):
            with patch("nxdrive.drive.client.proxy.ProxyResolver"):
                proxy = load_proxy(dao)
        assert isinstance(proxy, AutomaticProxy)
        assert proxy.pac_url == "http://proxy.local/proxy.pac"

    def test_load_none_proxy(self):
        dao = MagicMock()
        dao.get_config.side_effect = lambda key, **kw: (
            "None" if key == "proxy_config" else None
        )
        proxy = load_proxy(dao)
        assert isinstance(proxy, NoProxy)


# ------------------------------------------------------------------ save_proxy


class TestSaveProxy:
    def test_save_automatic(self):
        dao = MagicMock()
        proxy = MagicMock(spec=AutomaticProxy)
        proxy.category = "Automatic"
        proxy.pac_url = "http://proxy.local/proxy.pac"
        # isinstance check needs the real class
        real_proxy = AutomaticProxy.__new__(AutomaticProxy)
        real_proxy.pac_url = "http://proxy.local/proxy.pac"
        real_proxy.category = "Automatic"

        save_proxy(real_proxy, dao)
        dao.update_config.assert_any_call("proxy_config", "Automatic")
        dao.update_config.assert_any_call(
            "proxy_pac_url", "http://proxy.local/proxy.pac"
        )

    def test_save_manual(self):
        dao = MagicMock()
        dao.get_config.return_value = "device789"
        proxy = ManualProxy(url="http://proxy.local:3128")

        save_proxy(proxy, dao, token="mytoken")
        dao.update_config.assert_any_call("proxy_config", "Manual")
        # proxy_url should be called with encrypted bytes
        proxy_url_call = [
            c for c in dao.update_config.call_args_list if c[0][0] == "proxy_url"
        ]
        assert len(proxy_url_call) == 1
        encrypted_value = proxy_url_call[0][0][1]
        assert isinstance(encrypted_value, bytes)

    def test_save_manual_uses_device_id_if_no_token(self):
        dao = MagicMock()
        dao.get_config.return_value = "device-fallback"
        proxy = ManualProxy(url="http://proxy.local:3128")

        save_proxy(proxy, dao)
        dao.update_config.assert_any_call("proxy_config", "Manual")
        dao.get_config.assert_called_once_with("device_id")

    def test_save_system_proxy(self):
        dao = MagicMock()
        proxy = SystemProxy()
        save_proxy(proxy, dao)
        dao.update_config.assert_called_once_with("proxy_config", "System")

    def test_save_no_proxy(self):
        dao = MagicMock()
        proxy = NoProxy()
        save_proxy(proxy, dao)
        dao.update_config.assert_called_once_with("proxy_config", "None")


# ------------------------------------------------------------------ validate_proxy


class TestValidateProxy:
    def test_success(self):
        proxy = NoProxy()
        mock_response = MagicMock()
        mock_response.__enter__ = Mock(return_value=mock_response)
        mock_response.__exit__ = Mock(return_value=False)
        with patch(
            "nxdrive.drive.client.proxy.requests.get", return_value=mock_response
        ):
            with patch("nxdrive.drive.client.proxy.requests_verify", return_value=True):
                with patch(
                    "nxdrive.drive.client.proxy.client_certificate",
                    return_value=None,
                ):
                    result = validate_proxy(proxy, "http://example.com")
        assert result is True

    def test_oserror_returns_false(self):
        proxy = NoProxy()
        with patch(
            "nxdrive.drive.client.proxy.requests.get",
            side_effect=OSError("bad cert path"),
        ):
            with patch("nxdrive.drive.client.proxy.requests_verify", return_value=True):
                with patch(
                    "nxdrive.drive.client.proxy.client_certificate",
                    return_value=None,
                ):
                    result = validate_proxy(proxy, "http://example.com")
        assert result is False

    def test_attribute_error_returns_false(self):
        proxy = NoProxy()
        with patch(
            "nxdrive.drive.client.proxy.requests.get",
            side_effect=AttributeError("bad PAC"),
        ):
            with patch("nxdrive.drive.client.proxy.requests_verify", return_value=True):
                with patch(
                    "nxdrive.drive.client.proxy.client_certificate",
                    return_value=None,
                ):
                    result = validate_proxy(proxy, "http://example.com")
        assert result is False

    def test_generic_exception_returns_false(self):
        proxy = NoProxy()
        with patch(
            "nxdrive.drive.client.proxy.requests.get",
            side_effect=RuntimeError("something"),
        ):
            with patch("nxdrive.drive.client.proxy.requests_verify", return_value=True):
                with patch(
                    "nxdrive.drive.client.proxy.client_certificate",
                    return_value=None,
                ):
                    result = validate_proxy(proxy, "http://example.com")
        assert result is False
