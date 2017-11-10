# coding: utf-8
from nxdrive.client.remote_file_system_client import RemoteFileSystemClient
from nxdrive.logging_config import get_logger
from nxdrive.options import Options

log = get_logger(__name__)


class RemoteFilteredFileSystemClient(RemoteFileSystemClient):

    def __init__(self, server_url, user_id, device_id, client_version,
                 dao, proxies=None, proxy_exceptions=None,
                 password=None, token=None, repository=Options.remote_repo,
                 timeout=20, blob_timeout=None, cookie_jar=None,
                 upload_tmp_dir=None, check_suspended=None):
        super(RemoteFilteredFileSystemClient, self).__init__(
            server_url, user_id, device_id,
            client_version, proxies, proxy_exceptions,
            password, token, repository, timeout, blob_timeout, cookie_jar,
            upload_tmp_dir, check_suspended)
        self._dao = dao

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
                log.debug("Filtering item %r", item)
        return filtered
