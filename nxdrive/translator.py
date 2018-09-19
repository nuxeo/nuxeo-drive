# coding: utf-8
import codecs
import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

from PyQt5.QtCore import QTranslator, pyqtProperty, pyqtSignal, pyqtSlot

__all__ = ("Translator",)


class Translator(QTranslator):

    languageChanged = pyqtSignal()
    _singleton = None
    _current_lang: str = ""

    def __init__(self, manager: "Manager", path: str, lang: str = None) -> None:
        super().__init__()
        self._labels: Dict[str, Dict[str, str]] = {}
        self._manager = manager

        # Load from JSON
        for filename in os.listdir(path):
            filepath = os.path.join(path, filename)
            with codecs.open(filepath, encoding="utf-8") as fp:
                label = self.guess_label(filename)
                # Hebrew is not translated, skip it
                if label == "he":
                    continue
                self._labels[label] = json.loads(fp.read())

        # List language
        self._langs: Dict[str, Tuple[str, str]] = {}
        for key in self._labels:
            try:
                self._langs[key] = (key, self._labels[key]["LANGUAGE"])
            except KeyError:
                pass

        # Select one
        try:
            self._set(lang)
        except ValueError:
            self._set("en")
        self._fallback = self._labels["en"]

        Translator._singleton = self

    def translate(
        self, context: str, text: str, disambiguation: str = "", n: int = -1
    ) -> str:
        return self._get(text)

    @pyqtProperty(str, notify=languageChanged)
    def tr(self) -> str:
        return ""

    @staticmethod
    def guess_label(filename: str) -> str:
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
    def _tokenize(label: str, values: List[Any] = None) -> str:
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

    def _get(self, label: str, values: List[Any] = None) -> str:
        if label not in self._current:
            if label not in self._fallback:
                return label
            return self._tokenize(self._fallback[label], values)
        return self._tokenize(self._current[label], values)

    @pyqtSlot(str)
    def _set(self, lang: str) -> None:
        try:
            self._current = self._labels[lang]
        except KeyError:
            raise ValueError(f"Unknown language {lang!r}")
        else:
            if self._current_lang != lang:
                self._current_lang = lang
                self._manager.set_config("locale", lang)
                self.languageChanged.emit()

    def _locale(self) -> str:
        return self._current_lang

    def _languages(self) -> List[Tuple[str, str]]:
        return sorted(self._langs.values())

    def _translations(self) -> List[Tuple[str, Dict[str, str]]]:
        return sorted(self._labels.items())

    @staticmethod
    def set(lang: str) -> None:
        if Translator._singleton is None:
            raise RuntimeError("Translator not initialized")
        return Translator._singleton._set(lang)

    @staticmethod
    def format_date(date: datetime) -> str:
        return date.strftime(Translator.get("DATE_FORMAT"))

    @staticmethod
    def format_datetime(date: datetime) -> str:
        return date.strftime(Translator.get("DATETIME_FORMAT"))

    @staticmethod
    def locale() -> str:
        if Translator._singleton is None:
            raise RuntimeError("Translator not initialized")
        return Translator._singleton._locale()

    @staticmethod
    def get(label: str, values: List[str] = None) -> str:
        if Translator._singleton is None:
            raise RuntimeError("Translator not initialized")
        return Translator._singleton._get(label, values)

    @staticmethod
    def languages() -> List[Tuple[str, str]]:
        if Translator._singleton is None:
            raise RuntimeError("Translator not initialized")
        return Translator._singleton._languages()

    @staticmethod
    def translations() -> List[Tuple[str, Dict[str, str]]]:
        if Translator._singleton is None:
            raise RuntimeError("Translator not initialized")
        return Translator._singleton._translations()
