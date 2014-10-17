import subprocess
import urlparse
import urllib2

from gi.repository import Nautilus, GObject


class ExampleMenuProvider(GObject.GObject, Nautilus.MenuProvider):

    def __init__(self):
        pass

    def get_file_items(self, window, files):
        main_item = Nautilus.MenuItem(name='Nautilus::nuxe_drive',
                                      label='Nuxeo Drive',
                                      tip='Nuxeo Drive')
        main_item.connect("activate", self.open_metadata_view, files)
        return main_item,

    def open_metadata_view(self, menu, files):
        """Called when the user selects the menu."""
        file_uri = urlparse.urlparse(urllib2.unquote(files[0].get_uri())).path
        self.drive_exec(['metadata', '--file', file_uri])

    def drive_exec(self, cmds):
        # Add the ndrive command
        cmds.insert(0, "ndrive")
        p = subprocess.Popen(cmds, stdout=subprocess.PIPE)
        p.communicate()
