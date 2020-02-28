import pytest
import nxdrive.utils


@pytest.mark.parametrize(
    "url, result",
    [
        ("localhost", "http://localhost:8080/nuxeo"),
        ("127.0.0.1", "http://127.0.0.1:8080/nuxeo"),
        # HTTPS domain
        (
            "intranet-prerod.nuxeocloud.com",
            "https://intranet-preprod.nuxeocloud.com/nuxeo",
        ),
        # With additional parameters
        (
            "http://localhost:8080/nuxeo?TenantId=0xdeadbeaf",
            "http://localhost:8080/nuxeo?TenantId=0xdeadbeaf",
        ),
        (
            "http://127.0.0.1:8080/nuxeo?TenantId=0xdeadbeaf",
            "http://127.0.0.1:8080/nuxeo?TenantId=0xdeadbeaf",
        ),
        # Incomplete URL
        ("http://localhost", "http://localhost:8080/nuxeo"),
        ("http://127.0.0.1", "http://127.0.0.1:8080/nuxeo"),
        # Bad IP
        ("1.2.3.4", ""),
        # Bad protocol
        ("htto://localhost:8080/nuxeo", "http://localhost:8080/nuxeo"),
        ("htto://127.0.0.1:8080/nuxeo", "http://127.0.0.1:8080/nuxeo"),
    ],
)
def test_guess_server_url(nuxeo_url, url, result):
    if "127.0.0.1" not in nuxeo_url and "localhost" not in nuxeo_url:
        pytest.skip("Testing a non local server would fail")

    func = nxdrive.utils.guess_server_url
    if "intranet" in url:
        # The intranet is not stable enough to rely on it.
        # So we give a try and skip on error.
        try:
            assert func(url) == result
        except AssertionError as exc:
            pytest.skip(f"Intranet not stable ({exc})")
    else:
        assert func(url) == result
