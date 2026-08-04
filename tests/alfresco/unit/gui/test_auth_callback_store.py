"""Unit tests for nxdrive.alfresco.gui.auth_callback_store."""

import json
from unittest.mock import MagicMock

from nxdrive.alfresco.gui.auth_callback_store import (
    clear_auth_callback_params,
    load_auth_callback_params,
    save_auth_callback_params,
)


def _make_api():
    api = MagicMock()
    api._manager.dao.get_config.return_value = None
    return api


class TestSaveAuthCallbackParams:
    def test_persists_json(self):
        api = _make_api()
        params = {"code": "abc", "state": "xyz"}
        save_auth_callback_params(api, params)
        api._manager.dao.update_config.assert_called_once_with(
            "tmp_alfresco_auth_callback_params", json.dumps(params)
        )

    def test_empty_dict(self):
        api = _make_api()
        save_auth_callback_params(api, {})
        api._manager.dao.update_config.assert_called_once_with(
            "tmp_alfresco_auth_callback_params", "{}"
        )


class TestLoadAuthCallbackParams:
    def test_returns_dict_on_valid_json(self):
        api = _make_api()
        api._manager.dao.get_config.return_value = '{"code": "abc", "state": "xyz"}'
        result = load_auth_callback_params(api)
        assert result == {"code": "abc", "state": "xyz"}

    def test_returns_empty_when_no_config(self):
        api = _make_api()
        api._manager.dao.get_config.return_value = None
        result = load_auth_callback_params(api)
        assert result == {}

    def test_returns_empty_on_invalid_json(self):
        api = _make_api()
        api._manager.dao.get_config.return_value = "not-json{"
        result = load_auth_callback_params(api)
        assert result == {}

    def test_returns_empty_when_json_is_not_dict(self):
        api = _make_api()
        api._manager.dao.get_config.return_value = '["a", "b"]'
        result = load_auth_callback_params(api)
        assert result == {}

    def test_returns_empty_on_empty_string(self):
        api = _make_api()
        api._manager.dao.get_config.return_value = ""
        result = load_auth_callback_params(api)
        assert result == {}


class TestClearAuthCallbackParams:
    def test_calls_delete_config(self):
        api = _make_api()
        clear_auth_callback_params(api)
        api._manager.dao.delete_config.assert_called_once_with(
            "tmp_alfresco_auth_callback_params"
        )
