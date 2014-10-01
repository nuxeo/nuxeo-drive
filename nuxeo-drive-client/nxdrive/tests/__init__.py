'''
Created on 23 juin 2014

@author: Remi Cattiau
'''
from nxdrive.client.remote_filtered_file_system_client import RemoteFileSystemClient


class RemoteTestClient(RemoteFileSystemClient):
    '''
    classdocs
    '''

    def __init__(self, server_url, user_id, device_id, client_version,
                 session, proxies=None, proxy_exceptions=None,
                 password=None, token=None, repository="default",
                 ignored_prefixes=None, ignored_suffixes=None,
                 timeout=20, blob_timeout=None, cookie_jar=None,
                 upload_tmp_dir=None, check_suspended=None):
        '''
        Constructor
        '''
        super(RemoteTestClient, self).__init__(
            server_url, user_id, device_id,
            client_version, proxies, proxy_exceptions,
            password, token, repository, ignored_prefixes,
            ignored_suffixes, timeout, blob_timeout, cookie_jar,
            upload_tmp_dir, check_suspended)
        self._upload_remote_error = None

    def do_get(self, url, file_out=None):
        if self._upload_remote_error is None:
            super(RemoteTestClient, self).do_get(url, file_out)
        else:
            raise self._upload_remote_error

    def upload(self, batch_id, file_path, filename=None, file_index=0,
               mime_type=None):
        if self._upload_remote_error is None:
            super(RemoteTestClient, self).upload(batch_id,
                            file_path, filename, file_index, mime_type)
        else:
            raise self._upload_remote_error

    def make_remote_raise(self, error):
        """Make next calls to server raise the provided exception"""
        self._upload_remote_error = error
