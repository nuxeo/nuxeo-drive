import json
import os
import re
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from .qt.imports import QTranslator, pyqtProperty, pyqtSignal, pyqtSlot

__all__ = ("Translator",)

_CACHE: Dict[str, str] = {}


class Translator(QTranslator):

    languageChanged = pyqtSignal()
    singleton = None
    current_language: str = ""

    def __init__(self, path: Path, /, *, lang: str = None) -> None:
        super().__init__()
        self._labels: Dict[str, Dict[str, str]] = {}

        # Load from JSON
        for translation in path.iterdir():
            label = self.guess_label(translation.name)
            if label == "ar":
                # NXDRIVE-2385: Arabic is not yet ready
                continue
            self._labels[label] = json.loads(translation.read_text(encoding="utf-8"))

        # List language
        self.langs: Dict[str, Tuple[str, str]] = {}
        for key in self._labels:
            with suppress(KeyError):
                self.langs[key] = (key, self._labels[key]["LANGUAGE"])

        # Select one
        try:
            self.set_language(lang)
        except ValueError:
            self.set_language("en")
        self._fallback = self._labels["en"]

        Translator.singleton = self

    def translate(
        self, _context: str, text: str, _disambiguation: str, _n: int, /
    ) -> str:
        """
        *_context* is set by PyQt, e.g.: QQmlImportDatabase or Conflicts.
        *text* is the translation label or english PyQt error message, e.g.: EXTRA_FILE_COUNT or "is not a type".
        *_disambiguation* is set by PyQt, seems always None.
        *_n* is set by PyQt, seems always -1.

        *_context*, *_disambiguation* and *_n* are not used but required
        when the Translator is used inside QML.
        They also starts with a underscore to fix Vulture.
        """
        return self.get_translation(text)

    @pyqtProperty(str, notify=languageChanged)
    def tr(self) -> str:
        return ""

    @staticmethod
    def guess_label(filename: str, /) -> str:
        """
        Guess the language ID from a given filename.
            'i18n.json' -> 'en'
            'i18n-fr.json' -> 'fr'
            'i18n-es-ES.json' -> 'es-ES'
        """
        label = os.path.splitext(filename)[0].replace("i18n-", "")
        if label == "i18n":
            label = "en"
        return label

    @staticmethod
    def on_change(func: Callable, /) -> None:
        if not Translator.singleton:
            raise RuntimeError("Translator not initialized")
        Translator.singleton.languageChanged.connect(func)

    @staticmethod
    def _tokenize(label: str, /, *, values: List[Any] = None) -> str:
        """
        Format the label with its arguments.

        Qt strings differ from Python ones in two ways:
        - They use "%x" instead of "{x}" to add arguments through formatting,
        so we use a regex to substitute them.
        - Their arguments indexes start at 1 instead of 0, so we pass the
        values with an empty entry at the beginning.
        """
        if not values:
            return label

        result = re.sub(r"%(\d+)", r"{\1}", label)
        return result.format(*([""] + values))

    def get_translation(self, label: str, values: List[Any] = None) -> str:
        key = f"{label}{hash(tuple(values or ''))}"
        value = _CACHE.get(key)
        if value is None:
            token_label = self._current.get(label, self._fallback.get(label, label))
            value = (
                self._tokenize(token_label, values=values)
                if token_label != label
                else label
            )
            _CACHE[key] = value
        return value

    @pyqtSlot(str)  # from GeneralTab.qml
    def set_language(self, lang: str, /) -> None:
        try:
            self._current = self._labels[lang]
        except KeyError:
            raise ValueError(f"Unknown language {lang!r}")
        else:
            if self.current_language != lang:
                self.current_language = lang
                _CACHE.clear()
                self.languageChanged.emit()

    @staticmethod
    def set(lang: str, /) -> None:
        if not Translator.singleton:
            raise RuntimeError("Translator not initialized")
        Translator.singleton.set_language(lang)

    @staticmethod
    def format_datetime(date: datetime, /) -> str:
        return date.strftime(Translator.get("DATETIME_FORMAT"))

    @staticmethod
    def locale() -> str:
        if not Translator.singleton:
            raise RuntimeError("Translator not initialized")
        return Translator.singleton.current_language

    @staticmethod
    def get(label: str, /, *, values: List[Any] = None) -> str:
        if not Translator.singleton:
            raise RuntimeError("Translator not initialized")
        return Translator.singleton.get_translation(label, values=values)

    @staticmethod
    def languages() -> List[Tuple[str, str]]:
        if not Translator.singleton:
            raise RuntimeError("Translator not initialized")
        return sorted(Translator.singleton.langs.values())
