# coding: utf-8
import codecs
import json
import re


class Translator(object):

    _singleton = None

    def __init__(self, manager, filepath, lang=None):
        self._labels = None
        self._manager = manager

        # Load from JSON
        with codecs.open(filepath, encoding='utf-8') as fp:
            self._labels = json.loads(fp.read().lstrip('LABELS='))

        # List language
        self._langs = dict()
        for key in self._labels:
            try:
                self._langs[key] = (key, self._labels[key]['LANGUAGE'])
            except KeyError:
                pass

        # Select one
        try:
            self._set(lang)
        except ValueError:
            self._set('en')
        self._fallback = self._labels['en']
        Translator._singleton = self

    @staticmethod
    def _tokenize(label, values=None):
        if not values:
            return label

        result = label
        for token in re.findall(r'{{[^}]+}}', label):
            attr = token[2:-2].strip()
            try:
                value = values[attr]
            except KeyError:
                value = ''
            result = result.replace(token, value)
        return result

    def _get(self, label, values=None):
        if label not in self._current:
            if label not in self._fallback:
                return label
            return self._tokenize(self._fallback[label], values)
        return self._tokenize(self._current[label], values)

    def _set(self, lang):
        try:
            self._current = self._labels[lang]
        except KeyError:
            raise ValueError('Unknown language {!r}'.format(lang))
        else:
            self._current_lang = lang
            self._manager.set_config('locale', lang)

    def _locale(self):
        return self._current_lang

    def _languages(self):
        return sorted(self._langs.values())

    @staticmethod
    def set(lang):
        if Translator._singleton is None:
            raise RuntimeError('Translator not initialized')
        return Translator._singleton._set(lang)

    @staticmethod
    def format_date(date):
        return date.strftime(Translator.get("DATE_FORMAT"))

    @staticmethod
    def format_datetime(date):
        return date.strftime(Translator.get("DATETIME_FORMAT"))

    @staticmethod
    def locale():
        if Translator._singleton is None:
            raise RuntimeError('Translator not initialized')
        return Translator._singleton._locale()

    @staticmethod
    def get(label, values=None):
        if Translator._singleton is None:
            raise RuntimeError('Translator not initialized')
        return Translator._singleton._get(label, values)

    @staticmethod
    def languages():
        if Translator._singleton is None:
            raise RuntimeError('Translator not initialized')
        return Translator._singleton._languages()
