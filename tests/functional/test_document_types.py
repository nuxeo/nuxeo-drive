from pathlib import Path

from nxdrive.gui.constants import get_known_types_translations
from nxdrive.translator import Translator


def get_folder(folder) -> Path:
    return Path(__file__).parent.parent / "resources" / folder


def test_get_known_types_translations():
    Translator(get_folder("i18n"))
    assert Translator.locale() == "en"
    res = get_known_types_translations()

    known_folder_types = res.get("FOLDER_TYPES", {})
    known_file_types = res.get("FILE_TYPES", {})
    default_types = res.get("DEFAULT", {})

    assert known_folder_types["Folder"] == Translator.get("FOLDER")
    assert known_file_types["Audio"] == Translator.get("AUDIO")
    assert default_types["Automatic"] == Translator.get("AUTOMATICS")
