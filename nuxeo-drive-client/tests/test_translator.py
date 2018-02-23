# coding: utf-8
import os

import pytest

from nxdrive.wui.translator import Translator


class MockManager(object):
    def __init__(self):
        super(MockManager, self).__init__()
        self.called = False

    def set_config(self, locale, lang):
        self.called = True


def test_non_existing_file():
    with pytest.raises(OSError):
        Translator(MockManager(), get_folder('imagine'))


def test_load_file():
    manager = MockManager()
    Translator(manager, get_folder('i18n'))
    
    # Verify the call to save
    assert manager.called
    assert Translator.locale() == 'en'
    manager.called = False
    
    # Change to an existing language
    Translator.set('fr')
    assert manager.called
    assert Translator.locale() == 'fr'
    
    # Test unkown key
    assert Translator.get('BOUZOUF') == 'BOUZOUF'
    
    # Test fallback
    assert Translator.get('FALLBACK') == 'Fallback'
    manager.called = False
    
    # Try to switch to bad language
    with pytest.raises(ValueError):
        Translator.set('abcd')
    assert Translator.locale() == 'fr'
    
    # Nothing should be saved
    assert not manager.called
    
    # Go back to an existing one
    Translator.set('en')
    assert manager.called
    assert Translator.locale() == 'en'
    assert Translator.get('BOUZOUF') == 'BOUZOUF'

    # Change to an existing composed language
    Translator.set('de-DE')
    assert Translator.locale() == 'de-DE'
    assert Translator.get('CONNECTION_REFUSED') == 'Connection refused'


def test_non_iniialized():
    Translator._singleton = None
    with pytest.raises(RuntimeError):
        Translator.get('TEST')


def test_load_bad_language():
    Translator(MockManager(), get_folder('i18n'), 'zzzzzz')
    # Should fallback on en
    assert Translator.locale() == 'en'


def test_load_existing_language():
    Translator(MockManager(), get_folder('i18n'), 'fr')
    
    # Should not fallback on en
    assert Translator.locale() == 'fr'
    
    # Test the key fallback
    assert Translator.get('FALLBACK') == 'Fallback'
    assert Translator.get('LANGUAGE') == u'Fran\xe7ais'
    assert Translator.get('BOUZOUF') == 'BOUZOUF'


def test_token():
    options = dict()
    options['token_1'] = 'First Token'
    options['token_2'] = 'Another One'
    Translator(MockManager(), get_folder('i18n'))
    '''
    "TOKEN_NORMAL": "Language {{ token_1 }}",
    "TOKEN_DOUBLE": "{{ token_1 }} Language {{ token_2 }}",
    "TOKEN_UNKNOWN": "{{ token_unknown }} TOKEN",
    "TOKEN_WITH_NO_SPACE": "{{token_1}} TOKEN",
    "TOKEN_REPEAT": "{{token_1}} TOKEN {{ token_1 }}"
    '''
    assert Translator.get('TOKEN_NORMAL', options) == 'Language First Token'
    assert Translator.get('TOKEN_DOUBLE', options) == 'First Token Language Another One'
    assert Translator.get('TOKEN_UNKNOWN', options) == ' TOKEN'
    assert Translator.get('TOKEN_WITH_NO_SPACE', options) == 'First Token TOKEN'
    assert Translator.get('TOKEN_REPEAT', options) == 'First Token TOKEN First Token'


def get_folder(folder):
    return os.path.join(os.path.dirname(__file__), 'resources', folder)
