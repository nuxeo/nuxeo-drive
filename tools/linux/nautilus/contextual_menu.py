import subprocess
from urllib.parse import unquote, urlparse

from gi.repository import GObject, Nautilus


class NuxeoDriveMenuProvider(GObject.GObject, Nautilus.MenuProvider):
    def __init__(self):
        pass

    def get_file_items(self, _, files):
        # Access online
        access_item = Nautilus.MenuItem(
            name="Nautilus::nuxeodrive", label="Access online", tip="Nuxeo Drive"
        )
        access_item.connect("activate", self.access_online, files)

        # Copy share-link
        share_item = Nautilus.MenuItem(
            name="Nautilus::nuxeodrive", label="Copy share-link", tip="Nuxeo Drive"
        )
        share_item.connect("activate", self.copy_share_link, files)

        # Edit metadata
        metadata = Nautilus.MenuItem(
            name="Nautilus::nuxeodrive", label="Edit metadata", tip="Nuxeo Drive"
        )
        metadata.connect("activate", self.edit_metadata, files)

        return [access_item, share_item, metadata]

    def access_online(self, _, files):
        """Event fired by "Access online" menu entry."""
        file_uri = self._get_uri_path(files[0].get_uri())
        self.drive_exec(["view", "--file", file_uri])

    def copy_share_link(self, _, files):
        """Event fired by "Copy share-link" menu entry."""
        file_uri = self._get_uri_path(files[0].get_uri())
        self.drive_exec(["share-link", "--file", file_uri])

    def edit_metadata(self, _, files):
        """Event fired by "Edit metadata" menu entry."""
        file_uri = self._get_uri_path(files[0].get_uri())
        self.drive_exec(["metadata", "--file", file_uri])

    @staticmethod
    def drive_exec(cmds):
        """Launch Drive with given arguments."""
        p = subprocess.Popen(["ndrive"] + cmds, stdout=subprocess.PIPE)
        p.communicate()

    @staticmethod
    def _get_uri_path(uri):
        return unquote(urlparse(uri).path)
