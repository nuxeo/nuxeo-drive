# coding: utf-8
import argparse

import pytest
import requests

from nxdrive.options import Options

# Remove eventual logging callbacks
try:
    del Options.callbacks["log_level_console"]
except KeyError:
    pass
try:
    del Options.callbacks["log_level_file"]
except KeyError:
    pass


@Options.mock()
def test_batch_update_from_argparse():
    """ Simulate CLI args. """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--debug", default=True, action="store_true")
    parser.add_argument("--delay", default=0, type=int)
    options = parser.parse_args([])

    Options.update(options, setter="cli")
    assert Options.debug
    assert not Options.delay


@Options.mock()
def test_batch_update_from_dict():
    """ Simulate local and server conf files. """
    options = {"debug": True, "locale": "fr"}

    Options.update(options, setter="local")
    assert Options.debug
    assert Options.locale == "fr"


@Options.mock()
def test_batch_update_from_dict_with_unknown_option():
    options = {"debug": True, "foo": 42}

    with pytest.raises(KeyError):
        Options.update(options, setter="local", fail_on_error=True)
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
    assert not Options.callbacks


def test_getter():
    assert Options.options
    assert Options.delay == 30
    assert not Options.nothing


def test_error():
    with pytest.raises(KeyError):
        Options.set("no key", 42)

    Options.set("no key", 42, fail_on_error=False)

    with pytest.raises(TypeError):
        Options.set("delay", "foo")


@Options.mock()
def test_repr():
    assert repr(Options)

    Options.startup_page = "\xeat\xea"
    assert repr(Options)


@Options.mock()
def test_setters():
    """ Check setters level. """

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


@pytest.mark.skip("Waiting for NXDRIVE-1162")
def test_site_update_url():
    for url in (Options.update_site_url, Options.beta_update_site_url):
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
    assert str(Options) == "Options(startup_page[manual]='\xeat\xea')"

    Options.startup_page = "été"
    assert str(Options) == "Options(startup_page[manual]='\xe9t\xe9')"
