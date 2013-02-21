import os
import time

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient


class TestIntegrationEncoding(IntegrationTestCase):

    def setUp(self):
        super(TestIntegrationEncoding, self).setUp()

        self.ctl = self.controller_1
        self.ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
            self.user_1, self.password_1)
        self.sb = self.ctl.get_server_binding(self.local_nxdrive_folder_1)
        self.ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        self.syn = self.ctl.synchronizer
        self.syn.loop(delay=0.010, max_loops=1)

        self.remote_client = self.remote_document_client_1
        sync_root_folder = os.path.join(self.local_nxdrive_folder_1,
            self.workspace_title)
        self.local_client = LocalClient(sync_root_folder)

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

    def _synchronize_and_assert(self, expected_synchronized, wait=False):
        if wait:
            # Wait for audit changes to be detected after the 1 second step
            time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        n_synchronized = self.syn.update_synchronize_server(self.sb)
        self.assertEqual(n_synchronized, expected_synchronized)