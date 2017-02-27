'''
@author: Remi Cattiau
'''
import unittest
from nxdrive.wui.translator import Translator
import nxdrive
import os


class MockManager(object):
    def __init__(self):
        super(MockManager, self).__init__()
        self.called = False

    def set_config(self, locale, lang):
        self.called = True


class TranslatorTest(unittest.TestCase):

    def getFolder(self, file=None):
        return os.path.join(os.path.dirname(__file__), 'resources', file)

    def testNonExistingFile(self):
        self.assertRaises(IOError,Translator, MockManager(), self.getFolder('imagine.js'))

    def testLoadFile(self):
        manager = MockManager()
        Translator(manager, self.getFolder('i18n.js'))
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
        self.assertRaises(Exception, Translator.set, "de")
        self.assertEqual("fr", Translator.locale())
        self.assertFalse(manager.called)
        self.assertRaises(Exception, Translator.set, "es")
        self.assertEqual("fr", Translator.locale())
        # Nothing should be saved
        self.assertFalse(manager.called)
        # Go back to an existing one
        Translator.set("en")
        self.assertTrue(manager.called)
        self.assertEqual("en", Translator.locale())
        self.assertEqual("BOUZOUF", Translator.get("BOUZOUF"))

    def testNonIniialized(self):
        Translator._singleton = None
        self.assertRaises(Exception, Translator.get, "TEST")

    def testLoadBadFile(self):
        self.assertRaises(ValueError, Translator, MockManager(), self.getFolder('i18n-bad.js'))

    def testLoadBadLanguage(self):
        Translator(MockManager(),  self.getFolder('i18n.js'), "de")
        # Should fallback on en
        self.assertEqual("en", Translator.locale())

    def testLoadNonExistingLanguage(self):
        Translator(MockManager(),  self.getFolder('i18n.js'), "es")
        # Should fallback on en
        self.assertEqual("en", Translator.locale())

    def testLoadExistingLanguage(self):
        Translator(MockManager(),  self.getFolder('i18n.js'), "fr")
        # Should not fallback on en
        self.assertEqual("fr", Translator.locale())
        # Test the key fallback
        self.assertEqual("Fallback", Translator.get("FALLBACK"))
        self.assertEqual(u"Fran\xe7ais", Translator.get("LANGUAGE"))
        self.assertEqual("BOUZOUF", Translator.get("BOUZOUF"))

    def testToken(self):
        options = dict()
        options["token_1"] = "First Token"
        options["token_2"] = "Another One"
        Translator(MockManager(), self.getFolder('i18n.js'))
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