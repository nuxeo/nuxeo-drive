'''
Created on 19 mai 2014

@author: Remi Cattiau
'''
from nxdrive.client.remote_file_system_client import RemoteFileSystemClient
from nxdrive.client.common import DEFAULT_REPOSITORY_NAME
from nxdrive.logging_config import get_logger

log = get_logger(__name__)


class RemoteFilteredFileSystemClient(RemoteFileSystemClient):
    '''
    classdocs
    '''

    def __init__(self, server_url, user_id, device_id, client_version,
                 dao, proxies=None, proxy_exceptions=None,
                 password=None, token=None, repository=DEFAULT_REPOSITORY_NAME,
                 ignored_prefixes=None, ignored_suffixes=None,
                 timeout=20, blob_timeout=None, cookie_jar=None,
                 upload_tmp_dir=None, check_suspended=None):
        '''
        Constructor
        '''
        super(RemoteFilteredFileSystemClient, self).__init__(
            server_url, user_id, device_id,
            client_version, proxies, proxy_exceptions,
            password, token, repository, ignored_prefixes,
            ignored_suffixes, timeout, blob_timeout, cookie_jar,
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
