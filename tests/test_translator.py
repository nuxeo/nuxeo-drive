# coding: utf-8
from pathlib import Path

import pytest

from nxdrive.translator import Translator


class MockManager:
    def __init__(self):
        self.called = False

    def set_config(self, *args):
        self.called = True


def test_non_existing_file():
    with pytest.raises(OSError):
        Translator(MockManager(), get_folder("imagine"))


def test_load_file():
    manager = MockManager()
    Translator(manager, get_folder("i18n"))

    # Verify the call to save
    assert manager.called
    assert Translator.locale() == "en"
    manager.called = False

    # Change to an existing language
    Translator.set("fr")
    assert manager.called
    assert Translator.locale() == "fr"

    # Test unkown key
    assert Translator.get("BOUZOUF") == "BOUZOUF"

    # Test fallback
    assert Translator.get("FALLBACK") == "Fallback"
    manager.called = False

    # Try to switch to bad language
    with pytest.raises(ValueError):
        Translator.set("abcd")
    assert Translator.locale() == "fr"

    # Nothing should be saved
    assert not manager.called

    # Go back to an existing one
    Translator.set("en")
    assert manager.called
    assert Translator.locale() == "en"
    assert Translator.get("BOUZOUF") == "BOUZOUF"

    # Change to an existing composed language
    Translator.set("de-DE")
    assert Translator.locale() == "de-DE"
    assert Translator.get("CONNECTION_REFUSED") == "Connection refused"


def test_non_iniialized():
    Translator._singleton = None
    with pytest.raises(RuntimeError):
        Translator.get("TEST")


def test_load_bad_language():
    Translator(MockManager(), get_folder("i18n"), "zzzzzz")
    # Should fallback on en
    assert Translator.locale() == "en"


def test_load_existing_language():
    Translator(MockManager(), get_folder("i18n"), "fr")

    # Should not fallback on en
    assert Translator.locale() == "fr"

    # Test the key fallback
    assert Translator.get("FALLBACK") == "Fallback"
    assert Translator.get("LANGUAGE") == "Fran\xe7ais"
    assert Translator.get("BOUZOUF") == "BOUZOUF"


@pytest.mark.parametrize(
    "token, result",
    [
        ("TOKEN_NORMAL", "Language First Token"),
        ("TOKEN_DOUBLE", "First Token Language Another One"),
        ("TOKEN_WITH_NO_SPACE", "First Token TOKEN"),
        ("TOKEN_REPEAT", "First Token TOKEN First Token"),
    ],
)
def test_token(token, result):
    options = ["First Token", "Another One"]
    Translator(MockManager(), get_folder("i18n"))
    assert Translator.get(token, options) == result


def test_translate_twice():
    """ Check that the values array is not mutated. """
    Translator(MockManager(), get_folder("i18n"))
    values = ["value"]
    first = Translator.get("TOKEN_NORMAL", values)
    second = Translator.get("TOKEN_NORMAL", values)

    assert first == second
    assert values == ["value"]


def get_folder(folder) -> Path:
    return Path(__file__).parent / "resources" / folder
