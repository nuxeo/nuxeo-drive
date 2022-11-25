import pytest

from nxdrive.options import Options
from nxdrive.utils import get_verify


@pytest.mark.parametrize(
    "raw_value, expected_value",
    [
        (False, True),
        (True, False),
    ],
)
# @Options.mock()
def test_get_verify(raw_value, expected_value):
    old_ssl_no_verify = Options.ssl_no_verify
    Options.ssl_no_verify = raw_value
    verify = get_verify()
    print(">>>>>> ", raw_value, expected_value)
    print(
        ">>>>>> Options.ssl_no_verify : ",
        Options.ssl_no_verify,
        " exp: ",
        expected_value,
        "  Verify: ",
        verify,
    )
    if raw_value or Options.ca_bundle:
        assert verify is expected_value
    else:
        assert verify is not expected_value
    Options.ssl_no_verify = old_ssl_no_verify
