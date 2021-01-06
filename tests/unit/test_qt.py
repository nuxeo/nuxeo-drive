import pytest

from nxdrive.gui.folders_dialog import regexp_validator
from nxdrive.qt.constants import Acceptable, Invalid


@pytest.mark.parametrize(
    "input_data",
    [
        "simple_test_flder",
        "SIMPLE SPACED #1",
        "[WARNING]",
        "STRANĜE CHARS",
        "LIFE'S STRANGE",
    ],
)
def test_regexp_validator_should_pass(input_data):
    validator = regexp_validator()
    assert validator.validate(input_data, 0)[0] == Acceptable


@pytest.mark.parametrize(
    "input_data",
    [
        "test/*",
        '"[TEST]"',
        "TES|T",
        "SPACED TEST ?",
        "<code>",
        "TEST_FOLDER_ **",
        "SUB \\FOLDER",
    ],
)
def test_regexp_validator_should_not_pass(input_data):
    validator = regexp_validator()
    assert validator.validate(input_data, 0)[0] == Invalid
