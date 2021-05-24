import argparse
from contextlib import suppress
from unittest.mock import patch

import pytest
import requests
from sentry_sdk import configure_scope

from nxdrive.options import Options

# Remove eventual logging callbacks
with suppress(KeyError):
    del Options.callbacks["log_level_console"]
with suppress(KeyError):
    del Options.callbacks["log_level_file"]


def test_options_instantiation():
    with pytest.raises(RuntimeError):
        Options()


def test_ignored_option():
    Options.set("command", "foo")


@Options.mock()
def test_batch_update_from_argparse():
    """Simulate CLI args."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--debug", default=True, action="store_true")
    parser.add_argument("--delay", default=0, type=int)
    options = parser.parse_args([])

    Options.update(options, setter="cli")
    assert Options.debug
    assert not Options.delay


@Options.mock()
def test_batch_update_from_dict():
    """Simulate local and server conf files."""
    options = {"debug": True, "locale": "fr"}

    Options.update(options, setter="local")
    assert Options.debug
    assert Options.locale == "fr"


@Options.mock()
def test_batch_update_from_dict_with_unknown_option():
    options = {"debug": True, "foo": 42}

    with pytest.raises(RuntimeError) as err:
        Options.update(options, setter="local")
    msg = err.value.args[0]
    assert "foo" in msg
    assert "test.ini" not in msg
    assert "debugging" not in msg

    # Test the 'section' arg
    with pytest.raises(RuntimeError) as err:
        Options.update(options, setter="local", file="test.ini")
    msg = err.value.args[0]
    assert "foo" in msg
    assert "test.ini" in msg
    assert "debugging" not in msg

    # Test `file` and `section` args
    with pytest.raises(RuntimeError) as err:
        Options.update(options, setter="local", file="test.ini", section="debugging")
    msg = err.value.args[0]
    assert "foo" in msg
    assert "test.ini" in msg
    assert "debugging" in msg

    assert Options.debug
    assert not Options.foo


@Options.mock()
def test_bytes_conversion():
    Options.update_site_url = b"http://example.org"
    assert isinstance(Options.update_site_url, str)
    assert Options.update_site_url == "http://example.org"


@Options.mock()
def test_callback():
    def _callback(new_value):
        global checkpoint
        checkpoint = new_value

    global checkpoint
    checkpoint = 0

    Options.callbacks["delay"] = _callback
    Options.delay = 42
    assert checkpoint == 42

    # Simply trigger other callbacks, for coverage
    Options.cert_file = "unknown"
    Options.cert_file = __file__
    Options.deletion_behavior = "unsync"
    Options.deletion_behavior = "unknown"
    Options.use_sentry = False
    Options.is_frozen = True
    Options.use_sentry = False


@Options.mock()
def test_callback_bad_behavior():
    def _raises_from_callback(new_value):
        new_value / 0

    Options.callbacks["delay"] = _raises_from_callback
    with pytest.raises(ZeroDivisionError):
        Options.delay = 42


@Options.mock()
def test_callback_no_args():
    def _callback_with_no_args():
        pass

    Options.callbacks["delay"] = _callback_with_no_args
    with pytest.raises(TypeError):
        Options.delay = 42


def test_defaults():
    assert not Options.debug
    assert Options.delay == 30
    assert not Options.force_locale
    assert Options.startup_page == "drive_login.jsp"
    assert Options.callbacks


def test_getter():
    assert Options.options
    assert Options.delay == 30
    assert not Options.nothing


def test_error():
    with pytest.raises(RuntimeError):
        Options.set("no key", 42)

    with configure_scope() as scope:
        scope._should_capture = False
        Options.set("no key", 42, fail_on_error=False)
        Options.set("update_site_url", 42, setter="manual", fail_on_error=False)

    with pytest.raises(TypeError) as err:
        Options.set("delay", "foo")
    msg = err.value.args[0]
    assert "delay" in msg
    assert "test.ini" not in msg
    assert "debugging" not in msg

    # Test the 'section' arg
    with pytest.raises(TypeError) as err:
        Options.set("delay", "foo", file="test.ini")
    msg = err.value.args[0]
    assert "delay" in msg
    assert "test.ini" in msg
    assert "debugging" not in msg

    # Test `file` and `section` args
    with pytest.raises(TypeError) as err:
        Options.set("delay", "foo", file="test.ini", section="debugging")
    msg = err.value.args[0]
    assert "delay" in msg
    assert "test.ini" in msg
    assert "debugging" in msg


@Options.mock()
def test_list_conversion_and_original_values_updated():
    assert isinstance(Options.ignored_suffixes, tuple)
    assert "azerty" not in Options.ignored_suffixes
    current_len = len(Options.ignored_suffixes)

    Options.set("ignored_suffixes", ["azerty"], setter="manual")
    assert isinstance(Options.ignored_suffixes, tuple)
    assert "azerty" in Options.ignored_suffixes
    assert len(Options.ignored_suffixes) == current_len + 1

    new_values = {
        "ignored_files": ["bim", "bam", "boom", "zzzzzzzzzz"],
        "force_locale": "zh",
    }
    Options.update(new_values, setter="manual")
    assert isinstance(Options.ignored_files, tuple)
    assert "bim" in Options.ignored_files
    assert "bam" in Options.ignored_files
    assert "boom" in Options.ignored_files
    assert len(Options.ignored_files) > 4
    # Check it is sorted
    assert Options.ignored_files[-1] == "zzzzzzzzzz"


@Options.mock()
def test_repr():
    assert repr(Options)

    Options.startup_page = "\xeat\xea"
    assert repr(Options)


@Options.mock()
def test_setters():
    """Check setters level."""

    Options.set("delay", 1)
    assert Options.delay == 1

    Options.set("delay", 2, setter="server")
    assert Options.delay == 2

    Options.set("delay", 1)
    assert Options.delay == 2

    Options.set("delay", 3, setter="local")
    assert Options.delay == 3

    Options.set("delay", 2, setter="server")
    assert Options.delay == 3

    Options.set("delay", 42, setter="manual")
    assert Options.delay == 42

    Options.set("delay", 0, setter="local")
    assert Options.delay == 42

    Options.delay = 222
    assert Options.delay == 222


@Options.mock()
def test_server_and_local_config_with_default_value_forced():
    """Usecase:
    - The server defines some options.
    - The user decided to force default values for the same option.
    Result: The user choice must be the priority.
    """

    # The option is set to True by default
    assert Options.custom_metrics

    # The default arguments from the CLI are not taken into account
    Options.set("custom_metrics", True, setter="cli")
    assert str(Options) == "Options()"

    # The user has a config file setting the option to True,
    # even if this is the default value, it should be taken into account
    Options.set("custom_metrics", True, setter="local")
    assert str(Options) == "Options(custom_metrics[local]=True)"

    # Even further: the user has set the default value manually, it has the priority over all
    Options.set("custom_metrics", True, setter="manual")
    assert str(Options) == "Options(custom_metrics[manual]=True)"

    # The server's config has then no power
    Options.set("custom_metrics", False, setter="server")
    assert Options.custom_metrics


def test_site_update_url():
    url = f"{Options.update_site_url}/versions.yml"
    with requests.get(url) as resp:
        resp.raise_for_status()


@Options.mock()
def test_str():
    assert str(Options) == "Options()"

    Options.delay = 42
    assert str(Options) == "Options(delay[manual]=42)"


@Options.mock()
def test_str_utf8():
    Options.startup_page = "\xeat\xea"
    assert "startup_page[manual]='\xeat\xea'" in str(Options)

    Options.startup_page = "été"
    assert "startup_page[manual]='\xe9t\xe9'" in str(Options)


@Options.mock()
@pytest.mark.parametrize(
    "option, a_bad_value, a_good_value",
    [
        ("chunk_limit", -42, 42),
        ("chunk_size", 1024 * 5 + 1, 16),
        ("tmp_file_limit", -42.0, 42.0),
    ],
)
def test_validator(option, a_bad_value, a_good_value):
    # Setting a bad value is a no-op
    Options.set(option, a_bad_value)
    assert getattr(Options, option) != a_bad_value

    Options.set(option, a_good_value)
    assert getattr(Options, option) == a_good_value


@Options.mock()
def test_disabled_features(caplog):
    """Simple test for disabled features."""
    assert Options.feature_auto_update is True
    assert Options.feature_s3 is False

    with patch("nxdrive.options.DisabledFeatures", new=["auto_update"]):
        options = {"feature_auto_update": False, "feature_s3": True}
        Options.update(options, setter="manual")

    # feature_auto_update has been ignored as it is in DisabledFeatures
    assert Options.feature_auto_update is True

    # feature_s3 has been modified as expected
    assert Options.feature_s3 is True

    # Check that a warning has been fired
    record = caplog.records[0]
    assert record.levelname == "WARNING"
    assert record.message == "'feature_auto_update' cannot be changed."
