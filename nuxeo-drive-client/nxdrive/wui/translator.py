'''
@author: Remi Cattiau
'''
import json
import re


class Translator(object):
    '''
    classdocs
    '''

    _singleton = None

    def __init__(self, manager, filepath, lang=None):
        '''
        Constructor
        '''
        self._labels = None
        self._manager = manager
        # Load from JSON
        with open(filepath, "r") as fp:
            json_raw = fp.read()
        # Remove the setter for use in Angular
        json_raw = json_raw.replace("LABELS=", "")
        self._labels = json.loads(json_raw, 'utf-8')
        # List language
        self._langs = dict()
        for key in self._labels:
            if not "LANGUAGE" in self._labels[key]:
                continue
            self._langs[key] = (key, self._labels[key]["LANGUAGE"])
        # Select one
        if lang is None or not lang in self._langs:
            if "en" in self._labels:
                self._set("en")
                self._fallback = self._labels["en"]
            else:
                self._set(iter(self._labels).next())
                self._fallback = dict()
        else:
            self._set(lang)
            if "en" in self._langs:
                self._fallback = self._labels["en"]
        Translator._singleton = self

    def _tokenize(self, label, values=None):
        if values is None:
            return label
        result = label
        for token in re.findall(r'\{\{[^\}]+\}\}', label):
            attr = token[2:-2].strip()
            value = ""
            if attr in values:
                value = values[attr]
            result = result.replace(token, value)
        return result

    def _get(self, label, values=None):
        if not label in self._current:
            if not label in self._fallback:
                return label
            return self._tokenize(self._fallback[label], values)
        return self._tokenize(self._current[label], values)

    def _set(self, lang):
        if not lang in self._langs:
            raise Exception("Unkown language")
        self._current_lang = lang
        self._current = self._labels[lang]
        self._manager.set_config('locale', lang)

    def _locale(self):
        return self._current_lang

    def _languages(self):
        return self._langs.values()

    @staticmethod
    def set(lang):
        if Translator._singleton is None:
            raise Exception("Translator not initialized")
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
            raise Exception("Translator not initialized")
        return Translator._singleton._locale()

    @staticmethod
    def get(label, values=None):
        if Translator._singleton is None:
            raise Exception("Translator not initialized")
        return Translator._singleton._get(label, values)

    @staticmethod
    def languages():
        if Translator._singleton is None:
            raise Exception("Translator not initialized")
        return Translator._singleton._languages()
