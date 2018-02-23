import subprocess
import urlparse
import urllib2

from gi.repository import Nautilus, GObject


class NuxeoDriveMenuProvider(GObject.GObject, Nautilus.MenuProvider):
    def __init__(self):
        pass

    def get_file_items(self, window, files):
        _ = window
        main_item = Nautilus.MenuItem(name='Nautilus::nuxeodrive',
                                      label='Access online',
                                      tip='Nuxeo Drive')
        main_item.connect("activate", self.open_metadata_view, files)
        return main_item,

    def open_metadata_view(self, menu, files):
        """Called when the user selects the menu."""
        _ = menu
        file_uri = self._get_uri_path(files[0].get_uri())
        self.drive_exec(['metadata', '--file', file_uri])

    def drive_exec(self, cmds):
        """ Add the ndrive command. """
        cmds.insert(0, "ndrive")
        p = subprocess.Popen(cmds, stdout=subprocess.PIPE)
        p.communicate()

    def _get_uri_path(self, uri):
        return urllib2.unquote(urlparse.urlparse(uri).path)
