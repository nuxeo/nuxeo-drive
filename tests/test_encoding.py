# coding: utf-8
import os

import pytest

from nxdrive.client.local_client import FileInfo
from nxdrive.osi import AbstractOSIntegration
from .common import UnitTestCase


class TestEncoding(UnitTestCase):

    def setUp(self):
        self.engine_1.start()
        self.wait_sync()
        self.remote = self.remote_document_client_1
        self.local = self.local_1

    def test_filename_with_accents_from_server(self):
        self.remote.make_file(
            self.workspace,
            u'Nom sans accents.doc',
            u'Contenu sans accents.')
        self.remote.make_file(
            self.workspace,
            u'Nom avec accents \xe9 \xe8.doc',
            u'Contenu sans accents.')
        self.wait_sync(wait_for_async=True)

        content = self.local.get_content(u'/Nom sans accents.doc')
        assert content == u'Contenu sans accents.'

        content = self.local.get_content(u'/Nom avec accents \xe9 \xe8.doc')
        assert content == u'Contenu sans accents.'

    def test_filename_with_katakana(self):
        self.remote.make_file(
            self.workspace,
            u'Nom sans \u30bc\u30ec accents.doc',
            u'Contenu')
        self.local.make_file('/', u'Avec accents \u30d7 \u793e.doc', u'Contenu')
        self.wait_sync(wait_for_async=True)

        content = self.local.get_content(u'/Nom sans \u30bc\u30ec accents.doc')
        assert content == u'Contenu'
        content = self.remote.get_content(u'/Avec accents \u30d7 \u793e.doc')
        assert content == u'Contenu'

    def test_content_with_accents_from_server(self):
        data = u'Contenu avec caract\xe8res accentu\xe9s.'.encode('utf-8')
        self.remote.make_file(self.workspace, u'Nom sans accents.txt', data)
        self.wait_sync(wait_for_async=True)
        assert self.local.get_content(u'/Nom sans accents.txt') == data

    def test_filename_with_accents_from_client(self):
        self.local.make_file(
            '/', u'Avec accents \xe9 \xe8.doc', u'Contenu sans accents.')
        self.local.make_file('/', u'Sans accents.doc', u'Contenu sans accents.')
        self.wait_sync(wait_for_async=True)

        content = self.remote.get_content(u'/Avec accents \xe9 \xe8.doc')
        assert content == u'Contenu sans accents.'
        content = self.remote.get_content(u'/Sans accents.doc')
        assert content == u'Contenu sans accents.'

    def test_content_with_accents_from_client(self):
        data = u'Contenu avec caract\xe8res accentu\xe9s.'.encode('utf-8')
        self.local.make_file('/', u'Nom sans accents', data)
        self.wait_sync(wait_for_async=True)
        assert self.remote.get_content(u'/Nom sans accents') == data

    def test_name_normalization(self):
        filename = u'espace\xa0 et TM\u2122.doc'
        self.local.make_file('/', filename)
        self.wait_sync(wait_for_async=True)
        info = self.remote.get_info('/' + filename)
        assert info.name == filename

    @pytest.mark.skipif(AbstractOSIntegration.is_mac(),
                        reason="Normalization doesn't work on macOS")
    def test_fileinfo_normalization(self):
        self.engine_1.stop()
        name = u'Teste\u0301'
        self.local.make_file('/', name, 'Test')

        # FileInfo() will normalize the filename
        info = FileInfo(self.local.base_folder, '/' + name, False, 0)
        assert info.name != name

        # The encoding should be different,
        # cannot trust the get_children as they use FileInfo
        children = os.listdir(self.local.abspath('/'))
        assert len(children) == 1
        assert children[0] != name
