"""Unit tests for nxdrive.nuxeo.protocol module."""

import pytest

from nxdrive.nuxeo.protocol import (
    TOKEN_PATTERN,
    normalize_download_server_path,
    normalize_protocol_url,
    parse_direct_transfer_remote_path,
)


class TestNormalizeProtocolUrl:
    def test_already_canonical(self):
        assert normalize_protocol_url("nxdrive://token/edit") == "nxdrive://token/edit"

    def test_single_colon_no_slashes(self):
        assert normalize_protocol_url("nxdrive:token/edit") == "nxdrive://token/edit"

    def test_single_colon_single_slash(self):
        assert normalize_protocol_url("nxdrive:/token/edit") == "nxdrive://token/edit"

    def test_non_nxdrive_scheme_unchanged(self):
        assert normalize_protocol_url("https://example.com") == "https://example.com"

    def test_empty_string(self):
        assert normalize_protocol_url("") == ""


class TestParseDirectTransferRemotePath:
    def test_standard_url(self):
        url = "https://server.example.com/nuxeo/site/api/v1/path/default-domain/ws"
        result = parse_direct_transfer_remote_path(url)
        assert result == "/site/api/v1/path/default-domain/ws"

    def test_encoded_url(self):
        url = "https://server.example.com/nuxeo/path/My%20Folder"
        result = parse_direct_transfer_remote_path(url)
        assert result == "/path/My Folder"

    def test_missing_nuxeo_raises(self):
        with pytest.raises(ValueError, match="Missing /nuxeo"):
            parse_direct_transfer_remote_path("https://example.com/other/path")

    def test_with_whitespace(self):
        url = "  https://server.com/nuxeo/path/doc  "
        result = parse_direct_transfer_remote_path(url)
        assert result == "/path/doc"


class TestNormalizeDownloadServerPath:
    def test_already_has_nuxeo(self):
        result = normalize_download_server_path("server.com/nuxeo")
        assert result == "server.com/nuxeo"

    def test_missing_nuxeo_appended(self):
        result = normalize_download_server_path("server.com")
        assert result == "server.com/nuxeo"

    def test_trailing_slash_stripped(self):
        result = normalize_download_server_path("server.com/nuxeo/")
        assert result == "server.com/nuxeo"

    def test_with_port(self):
        result = normalize_download_server_path("server.com:8080")
        assert result == "server.com:8080/nuxeo"


class TestTokenPattern:
    def test_pattern_matches_non_slash(self):
        import re

        pattern = re.compile(TOKEN_PATTERN)
        assert pattern.fullmatch("abc123")
        assert pattern.fullmatch("token-with-dashes")
        assert not pattern.fullmatch("has/slash")
