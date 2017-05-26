# coding: utf-8
import os
import unittest

from nxdrive.wui.translator import Translator


class MockManager(object):
    def __init__(self):
        super(MockManager, self).__init__()
        self.called = False

    def set_config(self, locale, lang):
        self.called = True


class TranslatorTest(unittest.TestCase):

    def test_non_existing_file(self):
        self.assertRaises(IOError, Translator, MockManager(),
                          get_folder('imagine.js'))

    def test_load_file(self):
        manager = MockManager()
        Translator(manager, get_folder('i18n.js'))
        # Verify the call to save
        self.assertTrue(manager.called)
        self.assertEqual("en", Translator.locale())
        manager.called = False
        # Change to an existing language
        Translator.set("fr")
        self.assertTrue(manager.called)
        self.assertEqual("fr", Translator.locale())
        # Test unkown key
        self.assertEqual("BOUZOUF", Translator.get("BOUZOUF"))
        # Test fallback
        self.assertEqual("Fallback", Translator.get("FALLBACK"))
        manager.called = False
        # Try to switch to bad language
        self.assertRaises(ValueError, Translator.set, "abcd")
        self.assertEqual("fr", Translator.locale())
        # Nothing should be saved
        self.assertFalse(manager.called)
        # Go back to an existing one
        Translator.set("en")
        self.assertTrue(manager.called)
        self.assertEqual("en", Translator.locale())
        self.assertEqual("BOUZOUF", Translator.get("BOUZOUF"))

    def test_non_iniialized(self):
        Translator._singleton = None
        self.assertRaises(RuntimeError, Translator.get, "TEST")

    def test_load_bad_file(self):
        self.assertRaises(ValueError, Translator, MockManager(),
                          get_folder('i18n-bad.js'))

    def test_load_bad_language(self):
        Translator(MockManager(),  get_folder('i18n.js'), "zzzzzz")
        # Should fallback on en
        self.assertEqual("en", Translator.locale())

    def test_load_existing_language(self):
        Translator(MockManager(),  get_folder('i18n.js'), "fr")
        # Should not fallback on en
        self.assertEqual("fr", Translator.locale())
        # Test the key fallback
        self.assertEqual("Fallback", Translator.get("FALLBACK"))
        self.assertEqual(u"Fran\xe7ais", Translator.get("LANGUAGE"))
        self.assertEqual("BOUZOUF", Translator.get("BOUZOUF"))

    def test_token(self):
        options = dict()
        options["token_1"] = "First Token"
        options["token_2"] = "Another One"
        Translator(MockManager(), get_folder('i18n.js'))
        '''
        "TOKEN_NORMAL": "Language {{ token_1 }}",
        "TOKEN_DOUBLE": "{{ token_1 }} Language {{ token_2 }}",
        "TOKEN_UNKNOWN": "{{ token_unknown }} TOKEN",
        "TOKEN_WITH_NO_SPACE": "{{token_1}} TOKEN",
        "TOKEN_REPEAT": "{{token_1}} TOKEN {{ token_1 }}"
        '''
        self.assertEqual("Language First Token", Translator.get("TOKEN_NORMAL", options))
        self.assertEqual("First Token Language Another One", Translator.get("TOKEN_DOUBLE", options))
        self.assertEqual(" TOKEN", Translator.get("TOKEN_UNKNOWN", options))
        self.assertEqual("First Token TOKEN", Translator.get("TOKEN_WITH_NO_SPACE", options))
        self.assertEqual("First Token TOKEN First Token", Translator.get("TOKEN_REPEAT", options))


def get_folder(fname=None):
    return os.path.join(os.path.dirname(__file__), 'resources', fname)
