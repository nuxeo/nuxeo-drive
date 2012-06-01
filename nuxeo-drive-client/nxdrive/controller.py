"""Main API to perform Nuxeo Drive operations"""

import os.path
from nxdrive.model import Configuration


class Controller(object):
    """Manage configuration and perform Nuxeo Drive Operations"""

    def __init__(self, config_folder, process_type):
        self.config_folder = os.path.expanduser(config_folder)
        if not os.path.exists(self.config_folder):
            os.makedirs(self.config_folder)

        # TODO: handle a log file here?
        # if so, use 1 log file per process type (1 for sync daemon,
        # 1 for CLI controller, one for FS watcher...) so that they don't
        # concurrently write in the same log file
        self.process_type = process_type

    def start(self):
        """Start the Nuxeo Drive daemon"""
        # TODO

    def stop(self):
        """Stop the Nuxeo Drive daemon"""
        # TODO

    def status(self, files=()):
        """Fetch the status of some files

        If the list of files is empty, the status of the synchronization
        roots is returned.
        """
        # TODO
        return ()

    def attach(self, local_folder, nuxeo_url, username, password):
        """Bind a local folder to a remote nuxeo server"""
        # TODO
