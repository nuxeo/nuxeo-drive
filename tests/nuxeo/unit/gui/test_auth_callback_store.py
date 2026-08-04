"""Unit tests for nxdrive.nuxeo.gui.auth_callback_store module."""

import json
from unittest.mock import Mock

from nxdrive.nuxeo.gui.auth_callback_store import (
    clear_auth_callback_params,
    load_auth_callback_params,
    save_auth_callback_params,
)


class TestSaveAuthCallbackParams:
    def test_persists_json(self):
        api = Mock()
        params = {"code": "abc", "state": "xyz"}
        save_auth_callback_params(api, params)
        api._manager.dao.update_config.assert_called_once_with(
            "tmp_auth_callback_params", json.dumps(params)
        )


class TestLoadAuthCallbackParams:
    def test_returns_parsed_dict(self):
        api = Mock()
        api._manager.dao.get_config.return_value = json.dumps(
            {"code": "abc", "state": "xyz"}
        )
        result = load_auth_callback_params(api)
        assert result == {"code": "abc", "state": "xyz"}

    def test_returns_empty_dict_when_none(self):
        api = Mock()
        api._manager.dao.get_config.return_value = None
        assert load_auth_callback_params(api) == {}

    def test_returns_empty_dict_when_empty_string(self):
        api = Mock()
        api._manager.dao.get_config.return_value = ""
        assert load_auth_callback_params(api) == {}

    def test_returns_empty_dict_on_invalid_json(self):
        api = Mock()
        api._manager.dao.get_config.return_value = "not-valid-json{{"
        assert load_auth_callback_params(api) == {}

    def test_returns_empty_dict_when_not_a_dict(self):
        api = Mock()
        api._manager.dao.get_config.return_value = json.dumps(["a", "b"])
        assert load_auth_callback_params(api) == {}


class TestClearAuthCallbackParams:
    def test_deletes_config(self):
        api = Mock()
        clear_auth_callback_params(api)
        api._manager.dao.delete_config.assert_called_once_with(
            "tmp_auth_callback_params"
        )
