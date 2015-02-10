import os

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient


class TestEncoding(IntegrationTestCase):

    def setUp(self):
        super(TestEncoding, self).setUp()

        # Bind the server and root workspace
        self.setUpDrive_1(True)
        self.remote_client = self.remote_document_client_1
        self.local_client = self.local_client_1

    def test_filename_with_accents_from_server(self):
        self.remote_client.make_file(self.workspace,
            u'Nom sans accents.doc',
            u"Contenu sans accents.")
        self.remote_client.make_file(self.workspace,
            u'Nom avec accents \xe9 \xe8.doc',
            u"Contenu sans accents.")

        self._synchronize_and_assert(2, wait=True)

        self.assertEquals(self.local_client.get_content(
            u'/Nom sans accents.doc'),
            u"Contenu sans accents.")
        self.assertEquals(self.local_client.get_content(
            u'/Nom avec accents \xe9 \xe8.doc'),
            u"Contenu sans accents.")

    def test_filename_with_katakana_from_server(self):
        self.remote_client.make_file(self.workspace,
            u'Nom sans \u30bc\u30ec accents.doc',
            u"Contenu")
        self.local_client.make_file('/',
            u'Avec accents \u30d7 \u793e.doc',
            u"Contenu")

        self._synchronize_and_assert(2, wait=True)

        self.assertEquals(self.local_client.get_content(
            u'/Nom sans \u30bc\u30ec accents.doc'),
            u"Contenu")
        self.assertEquals(self.local_client.get_content(
            u'/Avec accents \u30d7 \u793e.doc'),
            u"Contenu")

    def test_content_with_accents_from_server(self):
        self.remote_client.make_file(self.workspace,
            u'Nom sans accents.txt',
            u"Contenu avec caract\xe8res accentu\xe9s.".encode('utf-8'))
        self._synchronize_and_assert(1, wait=True)
        self.assertEquals(self.local_client.get_content(
            u'/Nom sans accents.txt'),
            u"Contenu avec caract\xe8res accentu\xe9s.".encode('utf-8'))

    def test_filename_with_accents_from_client(self):
        self.local_client.make_file('/',
            u'Avec accents \xe9 \xe8.doc',
            u"Contenu sans accents.")
        self.local_client.make_file('/',
            u'Sans accents.doc',
            u"Contenu sans accents.")
        self._synchronize_and_assert(2)
        self.assertEquals(self.remote_client.get_content(
            u'/Avec accents \xe9 \xe8.doc'),
            u"Contenu sans accents.")
        self.assertEquals(self.remote_client.get_content(
            u'/Sans accents.doc'),
            u"Contenu sans accents.")

    def test_content_with_accents_from_client(self):
        self.local_client.make_file('/',
            u'Nom sans accents',
            u"Contenu avec caract\xe8res accentu\xe9s.".encode('utf-8'))
        self._synchronize_and_assert(1)
        self.assertEquals(self.remote_client.get_content(
            u'/Nom sans accents'),
            u"Contenu avec caract\xe8res accentu\xe9s.".encode('utf-8'))

    def test_name_normalization(self):
        self.local_client.make_file('/',
            u'espace\xa0 et TM\u2122.doc')
        self._synchronize_and_assert(1)
        self.assertEquals(self.remote_client.get_info(
            u'/espace\xa0 et TM\u2122.doc').name,
            u'espace\xa0 et TM\u2122.doc')

    def _synchronize_and_assert(self, expected_synchronized, wait=False):
        self.ndrive(self.ndrive_1)
