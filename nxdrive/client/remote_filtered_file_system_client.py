# coding: utf-8
from logging import getLogger

from .remote_file_system_client import RemoteFileSystemClient

log = getLogger(__name__)


class RemoteFilteredFileSystemClient(RemoteFileSystemClient):

    def is_filtered(self, path):
        return self._dao.is_filter(path)

    def get_children_info(self, fs_item_id):
        result = super(RemoteFilteredFileSystemClient, self).get_children_info(fs_item_id)
        # Need to filter the children result
        filtered = []
        for item in result:
            if not self.is_filtered(item.path):
                filtered.append(item)
            else:
                log.debug('Filtering item %r', item)
        return filtered
