# coding: utf-8
import codecs
import json
import os
import re


class Translator(object):

    _singleton = None

    def __init__(self, manager, path, lang=None):
        self._labels = None
        self._manager = manager

        # Load from JSON
        self._labels = {}
        for filename in os.listdir(path):
            filepath = os.path.join(path, filename)
            with codecs.open(filepath, encoding='utf-8') as fp:
                label = self.guess_label(filename)
                # Hebrew is not translated, skip it
                if label == 'he':
                    continue
                self._labels[label] = json.loads(fp.read())

        # List language
        self._langs = {}
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
    def guess_label(filename):
        """
        Guess the language ID from a given filename.
            'i18n.json' -> 'en'
            'i18n-fr.json' -> 'fr'
            'i18n-es-ES.json' -> 'es-ES'
        """
        label = os.path.splitext(filename)[0].replace('i18n-', '')
        if label == 'i18n':
            label = 'en'
        return label

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

            # For notifications, the text is limited to 200 characters
            # https://msdn.microsoft.com/en-us/library/windows/desktop/ee330740(v=vs.85).aspx
            # This is related to Windows, but we apply the truncation everywhere
            if attr in ('folder', 'name') and len(value) > 70:
                original = value
                try:
                    if isinstance(value, unicode):
                        value = value.encode('utf-8')
                    value = value.decode('utf-8')
                    value = u'{}…{}'.format(value[:30], value[-40:])
                except:
                    # If we failed to manage the unicode mess, just ignore it
                    value = original

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

    def _translations(self):
        return sorted(self._labels.items())

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

    @staticmethod
    def translations():
        if Translator._singleton is None:
            raise RuntimeError('Translator not initialized')
        return Translator._singleton._translations()
