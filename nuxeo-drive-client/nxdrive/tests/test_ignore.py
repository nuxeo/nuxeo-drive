import tempfile
import os
import shutil
from unittest import TestCase
from nxdrive.osi import AbstractOSIntegration
from nxdrive.client.local_client import LocalClient


class TestIgnoreFiles(TestCase):

    def setUp(self):
        super(TestIgnoreFiles, self).setUp()
        self.basedir = tempfile.mkdtemp(u'nxdrive')
        self.local_client = LocalClient(base_folder=self.basedir)
        self.local_client.make_file(u'/', u"#myfile#")
        self.local_client.make_file(u'/', u"Thumbs.db")
        self.local_client.make_file(u'/', u"desktop.ini")
        self.local_client.make_file(u'/', u"readme.txt")
        self.local_client.make_file(u'/', u"test.lock")
        self.local_client.make_file(u'/', u"test.swp")
        self.local_client.make_file(u'/', u"~bar.tmp")
        self.local_client.make_file(u'/', u"system.bk~")
        self.local_client.make_file(u'/', u"~$info.doc")
        self.local_client.make_file(u'/', u".update.sh")
        self.local_client.make_folder(u'/', u"mydir")
        self.local_client.make_file(u'/mydir', u"advise.txt")
        self.local_client.make_folder(u'/', u".yourdir")
        self.local_client.make_file(u'/.yourdir', u"proposal.pdf")
        if AbstractOSIntegration.is_windows():
            import win32con
            import win32api
            self.local_client.make_file(u'/', u"hidden-readme.txt")
            win32api.SetFileAttributes(u"/hidden-readme.txt", win32con.FILE_ATTRIBUTE_HIIDEN)
            self.local_client.make_folder(u'/', u"hidden-dir")
            win32api.SetFileAttributes(u"/hidden-dir", win32con.FILE_ATTRIBUTE_HIIDEN)
            self.local_client.make_file(u'/hidden-dir', u"nothidden.xsl")

    def tearDown(self):
        if os.path.exists(self.basedir):
            shutil.rmtree(self.basedir, ignore_errors=True)

    def test_ignored_files(self):
        self.assertTrue(self.local_client.is_ignored(u'/', u"#myfile#"), "#myfile# should have been ignored")
        self.assertTrue(self.local_client.is_ignored(u'/', u"Thumbs.db"), "Thumbs.db should have been ignored")
        self.assertTrue(self.local_client.is_ignored(u'/', u"desktop.ini"), "desktop.ini should have been ignored")
        self.assertFalse(self.local_client.is_ignored(u'/', u"readme.txt"), "readme.txt should not have been ignored")
        self.assertTrue(self.local_client.is_ignored(u'/', u"test.lock"), "test.lock should have been ignored")
        self.assertTrue(self.local_client.is_ignored(u'/', u"test.swp"), "test.swp should have been ignored")
        self.assertTrue(self.local_client.is_ignored(u'/', u"~bar.tmp"), "~bar.tmp should have been ignored")
        self.assertTrue(self.local_client.is_ignored(u'/', u"system.bk~"), "system.bk~ should have been ignored")
        self.assertTrue(self.local_client.is_ignored(u'/', u"~$info.doc"), "~$info.doc should have been ignored")
        self.assertTrue(self.local_client.is_ignored(u'/', u".update.sh"), ".update.sh should have been ignored")
        self.assertFalse(self.local_client.is_ignored(u'/mydir', u"advise.txt"),
                         "advise.txt should have not been ignored")
        self.assertTrue(self.local_client.is_ignored(u'/.yourdir', u"proposal.pdf"),
                        "proposal.pdf should have been ignored")

    def test_update_prefixes_and_suffixes(self):
        self.local_client = LocalClient(base_folder=self.basedir, ignored_prefixes=('.',), ignored_suffixes=('.tmp',))
        self.assertTrue(self.local_client.is_ignored(u'/', u"#myfile#"), "#myfile# should have been ignored")
        self.assertFalse(self.local_client.is_ignored(u'/', u"Thumbs.db"), "Thumbs.db should not have been ignored")
        self.assertFalse(self.local_client.is_ignored(u'/', u"desktop.ini"), "desktop.ini should not have been ignored")
        self.assertFalse(self.local_client.is_ignored(u'/', u"readme.txt"), "readme.txt should not have been ignored")
        self.assertFalse(self.local_client.is_ignored(u'/', u"test.lock"), "test.lock should not have been ignored")
        self.assertFalse(self.local_client.is_ignored(u'/', u"test.swp"), "test.swp should not have been ignored")
        self.assertTrue(self.local_client.is_ignored(u'/', u"~bar.tmp"), "~bar.tmp should have been ignored")
        self.assertFalse(self.local_client.is_ignored(u'/', u"system.bk~"), "system.bk~ should not have been ignored")
        self.assertFalse(self.local_client.is_ignored(u'/', u"~$info.doc"), "~$info.doc should not have been ignored")
        self.assertTrue(self.local_client.is_ignored(u'/', u".update.sh"), ".update.sh should have been ignored")
        self.assertFalse(self.local_client.is_ignored(u'/mydir', u"advise.txt"),
                         "advise.txt should have not been ignored")
        self.assertTrue(self.local_client.is_ignored(u'/.yourdir', u"proposal.pdf"),
                         "proposal.pdf should have been ignored")
