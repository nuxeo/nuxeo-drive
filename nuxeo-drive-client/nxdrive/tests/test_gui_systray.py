# coding: utf-8

from tempfile import mkdtemp
from unittest import SkipTest, TestCase

from PyQt4.QtCore import Qt, QPoint
from PyQt4.QtTest import QTest
from mock import Mock

from nxdrive.logging_config import configure, get_logger
from nxdrive.manager import Manager
from nxdrive.tests.common import clean_dir
from nxdrive.wui.application import Application


class SystemTrayMenu(TestCase):

    # Delay, in msec, before and after each mouse action
    delay = 100

    @classmethod
    def setUpClass(cls):

        def configure_logger():
            configure(console_level='TRACE',
                      command_name='test',
                      force_configure=True)

        # Configure test logger
        configure_logger()
        cls.log = get_logger(__name__)

        cls.folder = mkdtemp(u'-nxdrive-tests-gui-systray')
        options = Mock()
        options.debug = False
        options.force_locale = None
        options.proxy_server = None
        options.log_level_file = None
        options.update_site_url = None
        options.beta_update_site_url = None
        options.nxdrive_home = cls.folder

        cls.manager = Manager(options)
        cls.app = Application(cls.manager, options)

        # Close the settings window, if opened (on fresh install)
        try:
            cls.app.uniqueDialogs['settings'].close()
        except KeyError:
            pass

        QTest.qWait(1000)

        cls.icon = cls.app._tray_icon
        cls.menu = cls.app.tray_icon_menu

    @classmethod
    def tearDownClass(cls):
        # Remove singleton
        cls.manager.dispose_db()
        Manager._singleton = None

        clean_dir(cls.folder)

    def test_0_icon_is_visible(self):
        ''' Note: the method name starts with a "0" to be the first executed.
            No system tray icon => no tests.
        '''

        self.log.debug('Systray icon should be visible')
        self.assertTrue(self.icon.isVisible())

        geo = self.icon.geometry()
        self.log.trace('Systray icon (%s, %s) at position (%s, %s)', geo.width(), geo.height(), geo.x(), geo.y())
        # Simple tests for this Qt5 bug: https://bugreports.qt.io/browse/QTBUG-32811
        # If it fails here, we cannot do anything but upgrade Qt version (from the customer side)
        self.assertTrue(geo.width() > 1)
        self.assertTrue(geo.height() > 1)

    def test_icon_click_left(self):
        raise SkipTest('To debug: cannot trigger a mouse click on the icon ...')

        self.log.debug('Left click on the icon should open the menu')
        geo = self.icon.geometry()
        pos = QPoint(geo.x() + geo.width() // 2, geo.y() + geo.height() // 2)
        self.log.trace('Move mouse at position (%s, %s)', pos.x(), pos.y())
        QTest.mouseMove(self.menu, pos=pos, delay=self.delay)

        self.log.trace('Simulate left click on the icon')
        QTest.mouseClick(self.menu.dialog, Qt.LeftButton, pos=pos, delay=self.delay)

        QTest.qWait(1000)
        self.assertTrue(self.menu.isVisible())

        self.log.debug('Another left click on the icon should close the menu')
        # click!
        self.assertFalse(self.menu.isVisible())
