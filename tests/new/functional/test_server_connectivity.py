"""Functional tests for server connectivity and dynamic class loading.

Tests cover:
- Nuxeo server connectivity (using env-var credentials)
- Alfresco server connectivity (using env-var credentials)
- Dynamic class instantiation via ServerTypeConfig
- Auth factory execution for both server types
- End-to-end registration → load_class → issubclass chain

Credentials must be provided via environment variables:
  NXDRIVE_TEST_NUXEO_URL, NXDRIVE_TEST_USERNAME, NXDRIVE_TEST_PASSWORD
  ALFRESCO_TEST_URL, ALFRESCO_TEST_USERNAME, ALFRESCO_TEST_PASSWORD
"""

import os

import pytest
import requests

from nxdrive.drive.server_type import detect_by_url, get, load_class
from nxdrive.drive.utils import get_verify

# ------------------------------------------------------------------ env helpers


def _nuxeo_url():
    return os.environ.get("NXDRIVE_TEST_NUXEO_URL", "")


def _nuxeo_creds():
    return (
        os.environ.get("NXDRIVE_TEST_USERNAME", ""),
        os.environ.get("NXDRIVE_TEST_PASSWORD", ""),
    )


def _alfresco_url():
    return os.environ.get("ALFRESCO_TEST_URL", "")


def _alfresco_creds():
    return (
        os.environ.get("ALFRESCO_TEST_USERNAME", ""),
        os.environ.get("ALFRESCO_TEST_PASSWORD", ""),
    )


skip_no_nuxeo = pytest.mark.skipif(
    not _nuxeo_url(), reason="NXDRIVE_TEST_NUXEO_URL not set"
)
skip_no_alfresco = pytest.mark.skipif(
    not _alfresco_url(), reason="ALFRESCO_TEST_URL not set"
)


# ------------------------------------------------------------------ Nuxeo connectivity


@skip_no_nuxeo
def test_nuxeo_server_reachable():
    """Verify the Nuxeo server is reachable."""
    url = _nuxeo_url().rstrip("/") + "/api/v1/path/"
    user, pwd = _nuxeo_creds()
    resp = requests.get(url, auth=(user, pwd), verify=get_verify(), timeout=30)
    assert resp.status_code in (
        200,
        401,
        403,
    ), f"Unexpected status {resp.status_code} from {url}"


@skip_no_nuxeo
def test_nuxeo_detect_by_url():
    """detect_by_url should identify a Nuxeo URL."""
    url = _nuxeo_url()
    cfg = detect_by_url(url)
    assert cfg.key == "NUXEO"


@skip_no_nuxeo
def test_nuxeo_auth_factory_token():
    """Nuxeo auth_factory with a string token should produce TokenAuthentication."""
    cfg = get("NUXEO")
    url = _nuxeo_url()
    auth = cfg.auth_factory(url, "fake-token-string")
    assert auth is not None
    assert "Token" in type(auth).__name__


@skip_no_nuxeo
def test_nuxeo_auth_factory_oauth2():
    """Nuxeo auth_factory with a dict token should produce OAuthentication."""
    cfg = get("NUXEO")
    url = _nuxeo_url()
    auth = cfg.auth_factory(url, {"access_token": "fake", "refresh_token": "fake"})
    assert auth is not None
    assert "OAuthentication" in type(auth).__name__


@skip_no_nuxeo
def test_nuxeo_engine_class_loadable():
    """Verify Nuxeo Engine class can be loaded and is a proper subclass."""
    from nxdrive.drive.engine.engine import Engine as BaseEngine

    cfg = get("NUXEO")
    cls = load_class(cfg.engine_class_path)
    assert cls is not None
    assert issubclass(cls, BaseEngine)


@skip_no_nuxeo
def test_nuxeo_direct_edit_class_loadable():
    """Verify Nuxeo DirectEdit class can be loaded and is a proper subclass."""
    from nxdrive.drive.direct_edit import DirectEdit as Base

    cfg = get("NUXEO")
    cls = load_class(cfg.direct_edit_class_path)
    assert cls is not None
    assert issubclass(cls, Base)


@skip_no_nuxeo
def test_nuxeo_direct_download_class_loadable():
    """Verify Nuxeo DirectDownload class can be loaded and is a proper subclass."""
    from nxdrive.drive.direct_download import DirectDownload as Base

    cfg = get("NUXEO")
    cls = load_class(cfg.direct_download_class_path)
    assert cls is not None
    assert issubclass(cls, Base)


@skip_no_nuxeo
def test_nuxeo_workflow_class_loadable():
    """Verify Nuxeo Workflow class can be loaded and is a proper subclass."""
    from nxdrive.drive.client.workflow import Workflow as Base

    cfg = get("NUXEO")
    cls = load_class(cfg.workflow_class_path)
    assert cls is not None
    assert issubclass(cls, Base)


@skip_no_nuxeo
def test_nuxeo_nuxeo_client_api_login():
    """Verify we can connect to Nuxeo via the nuxeo Python client.

    If the server requires OAuth2 instead of basic auth, the client will
    raise Unauthorized — we still verify the connection was established
    and the correct error type is returned (not a network error).
    """
    from nuxeo.client import Nuxeo
    from nuxeo.exceptions import Unauthorized

    url = _nuxeo_url()
    user, pwd = _nuxeo_creds()
    server = Nuxeo(auth=(user, pwd), host=url, verify=get_verify())
    try:
        current_user = server.client.request("GET", "api/v1/me")
        # Basic auth worked
        assert current_user is not None
        assert current_user.get("id") or current_user.get("entity-type")
    except Unauthorized:
        # Server requires OAuth2 — basic auth rejected but server is reachable
        pass


# ------------------------------------------------------------------ Alfresco connectivity


@skip_no_alfresco
def test_alfresco_server_reachable():
    """Verify the Alfresco server is reachable."""
    url = _alfresco_url().rstrip("/")
    # Try multiple common endpoints
    for endpoint in [
        "/api/discovery",
        "/api/-default-/public/alfresco/versions/1",
        "/alfresco/api/-default-/public/alfresco/versions/1",
        "",
    ]:
        test_url = url + endpoint
        try:
            resp = requests.get(test_url, verify=get_verify(), timeout=30)
            if resp.status_code in (200, 401, 403):
                return  # Server is reachable
        except requests.RequestException:
            continue
    # If we get here, at least the base URL should respond
    resp = requests.get(url, verify=get_verify(), timeout=30)
    assert resp.status_code < 500, f"Server not reachable at {url}"


@skip_no_alfresco
def test_alfresco_detect_by_url():
    """detect_by_url should identify an Alfresco URL (fallback)."""
    url = _alfresco_url()
    cfg = detect_by_url(url)
    assert cfg.key == "ALFRESCO"


@skip_no_alfresco
def test_alfresco_auth_factory_token():
    """Alfresco auth_factory with a string token should produce TokenAuthentication."""
    cfg = get("ALFRESCO")
    url = _alfresco_url()
    auth = cfg.auth_factory(url, "fake-token-string")
    assert auth is not None
    assert "Token" in type(auth).__name__


@skip_no_alfresco
def test_alfresco_auth_factory_oauth2():
    """Alfresco auth_factory with a dict token should produce AlfrescoOAuthentication."""
    cfg = get("ALFRESCO")
    url = _alfresco_url()
    auth = cfg.auth_factory(url, {"access_token": "fake", "refresh_token": "fake"})
    assert auth is not None
    assert "Alfresco" in type(auth).__name__


@skip_no_alfresco
def test_alfresco_engine_class_loadable():
    """Verify Alfresco Engine class can be loaded."""
    cfg = get("ALFRESCO")
    cls = load_class(cfg.engine_class_path)
    assert cls is not None
    assert cls.__name__ == "AlfrescoEngine"


@skip_no_alfresco
def test_alfresco_disabled_features():
    """Verify Alfresco disabled features include direct_edit etc."""
    cfg = get("ALFRESCO")
    assert "direct_edit" in cfg.disabled_features
    assert "direct_transfer" in cfg.disabled_features


# ------------------------------------------------------------------ cross-server


def test_server_types_do_not_overlap_engine_type():
    """Each server type has a unique engine_type."""
    from nxdrive.drive.server_type import all_configs

    configs = all_configs()
    engine_types = [c.engine_type for c in configs.values()]
    assert len(engine_types) == len(set(engine_types))


def test_server_types_do_not_overlap_db_prefix():
    """Each server type has a unique db_prefix."""
    from nxdrive.drive.server_type import all_configs

    configs = all_configs()
    prefixes = [c.db_prefix for c in configs.values()]
    assert len(prefixes) == len(set(prefixes))


def test_server_types_do_not_overlap_home_dir():
    """Each server type has a unique home_dir."""
    from nxdrive.drive.server_type import all_configs

    configs = all_configs()
    dirs = [c.home_dir for c in configs.values()]
    assert len(dirs) == len(set(dirs))
