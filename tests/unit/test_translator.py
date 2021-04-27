from pathlib import Path

import pytest

from nxdrive.translator import Translator


def get_folder(folder) -> Path:
    return Path(__file__).parent.parent / "resources" / folder


def test_non_existing_file():
    with pytest.raises(OSError):
        Translator(get_folder("imagine"))


def test_load_file():
    Translator(get_folder("i18n"))

    # Verify the call to save
    assert Translator.locale() == "en"

    # Change to an existing language
    Translator.set("fr")
    assert Translator.locale() == "fr"

    # Test unknown key
    assert Translator.get("BOUZOUF") == "BOUZOUF"

    # Test fallback
    assert Translator.get("FALLBACK") == "Fallback"

    # Try to switch to bad language
    with pytest.raises(ValueError):
        Translator.set("abcd")
    assert Translator.locale() == "fr"

    # Go back to an existing one
    Translator.set("en")
    assert Translator.locale() == "en"
    assert Translator.get("BOUZOUF") == "BOUZOUF"

    # Change to an existing composed language
    Translator.set("de")
    assert Translator.locale() == "de"
    assert Translator.get("CONNECTION_REFUSED") == "Connection refused"


def test_non_initialized():
    Translator.singleton = None
    with pytest.raises(RuntimeError):
        Translator.get("TEST")


def test_load_bad_language():
    Translator(get_folder("i18n"), lang="zzzzzz")
    # Should fallback on en
    assert Translator.locale() == "en"


def test_load_existing_language():
    Translator(get_folder("i18n"), lang="fr")

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
    Translator(get_folder("i18n"))
    assert Translator.get(token, values=options) == result


def test_translate_twice():
    """Check that the values array is not mutated."""
    Translator(get_folder("i18n"))
    values = ["value"]
    first = Translator.get("TOKEN_NORMAL", values=values)
    second = Translator.get("TOKEN_NORMAL", values=values)

    assert first == second
    assert values == ["value"]


def test_translate_twice_different_values():
    """Check that the values array is taken into account in the LRU cache."""
    Translator(get_folder("i18n"))
    values1 = ["value1"]
    values2 = ["value2"]
    first = Translator.get("TOKEN_NORMAL", values=values1)
    second = Translator.get("TOKEN_NORMAL", values=values2)

    assert first != second


def test_languages():
    """Check that all languages are well retrieved."""
    folder = Path(__file__).parent.parent.parent / "nxdrive" / "data" / "i18n"
    Translator(folder)
    expected = [
        ("de", "Deutsch"),
        ("en", "English"),
        ("es", "Español"),
        ("eu", "Euskara"),
        ("fr", "Français"),
        ("id", "Bahasa Indonesia"),
        ("it", "Italiano"),
        ("ja", "日本語"),
        ("nl", "Nederlands"),
        ("pl", "Polski"),
        ("sv", "Svenska"),
    ]
    languages = Translator.languages()
    assert languages == expected
    # NXDRIVE-2385: - 1 for Arabic
    assert len(languages) == len(list(folder.glob("*.json"))) - 1
