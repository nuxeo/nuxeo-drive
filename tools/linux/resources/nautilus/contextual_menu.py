import subprocess
import urlparse
import urllib2

from gi.repository import Nautilus, GObject


class NuxeoDriveMenuProvider(GObject.GObject, Nautilus.MenuProvider):
    def __init__(self):
        pass

    def get_file_items(self, window, files):
        _ = window
        access_item = Nautilus.MenuItem(name='Nautilus::nuxeodrive',
                                        label='Access online',
                                        tip='Nuxeo Drive')
        access_item.connect('activate', self.open_metadata_view, files)
        share_item = Nautilus.MenuItem(name='Nautilus::nuxeodrive',
                                       label='Copy share-link',
                                       tip='Nuxeo Drive')
        share_item.connect('activate', self.copy_share_link, files)
        return [access_item, share_item]

    def open_metadata_view(self, menu, files):
        """Called when the user selects the menu item `Access online`."""
        _ = menu
        file_uri = self._get_uri_path(files[0].get_uri())
        self.drive_exec(['metadata', '--file', file_uri])

    def copy_share_link(self, menu, files):
        """Called when the user selects the menu item `Copy share-link`."""
        _ = menu
        file_uri = self._get_uri_path(files[0].get_uri())
        self.drive_exec(['share-link', '--file', file_uri])

    def drive_exec(self, cmds):
        """ Add the ndrive command. """
        cmds.insert(0, 'ndrive')
        p = subprocess.Popen(cmds, stdout=subprocess.PIPE)
        p.communicate()

    def _get_uri_path(self, uri):
        return urllib2.unquote(urlparse.urlparse(uri).path)
