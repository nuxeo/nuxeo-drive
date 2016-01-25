'''
Created on 23 juin 2014

@author: Remi Cattiau
'''
from nxdrive.client.remote_filtered_file_system_client import RemoteFileSystemClient
from nxdrive.client.common import DEFAULT_REPOSITORY_NAME


class RemoteTestClient(RemoteFileSystemClient):
    '''
    classdocs
    '''

    def __init__(self, server_url, user_id, device_id, client_version,
                 session, proxies=None, proxy_exceptions=None,
                 password=None, token=None, repository=DEFAULT_REPOSITORY_NAME,
                 ignored_prefixes=None, ignored_suffixes=None,
                 timeout=20, blob_timeout=None, cookie_jar=None,
                 upload_tmp_dir=None, check_suspended=None):
        self._download_remote_error = None
        self._upload_remote_error = None
        self._server_error = None
        '''
        Constructor
        '''
        super(RemoteTestClient, self).__init__(
            server_url, user_id, device_id,
            client_version, proxies, proxy_exceptions,
            password, token, repository, ignored_prefixes,
            ignored_suffixes, timeout, blob_timeout, cookie_jar,
            upload_tmp_dir, check_suspended)

    def do_get(self, url, file_out=None, digest=None, digest_algorithm=None):
        if self._download_remote_error is None:
            return super(RemoteTestClient, self).do_get(url, file_out=file_out, digest=digest,
                                                        digest_algorithm=digest_algorithm)
        else:
            raise self._download_remote_error

    def upload(self, batch_id, file_path, filename=None, file_index=0,
               mime_type=None):
        if self._upload_remote_error is None:
            return super(RemoteTestClient, self).upload(batch_id, file_path, filename=filename, file_index=file_index,
                                                        mime_type=mime_type)
        else:
            raise self._upload_remote_error

    def fetch_api(self):
        if self._server_error is None:
            return super(RemoteTestClient, self).fetch_api()
        else:
            raise self._server_error

    def execute(self, command, url=None, op_input=None, timeout=-1,
                check_params=True, void_op=False, extra_headers=None,
                file_out=None, **params):
        if self._server_error is None:
            return super(RemoteTestClient, self).execute(command, url=url, op_input=op_input, timeout=timeout,
                                                         check_params=check_params, void_op=void_op,
                                                         extra_headers=extra_headers, file_out=file_out, **params)
        else:
            raise self._server_error

    def make_download_raise(self, error):
        """Make next calls to do_get raise the provided exception"""
        self._download_remote_error = error

    def make_upload_raise(self, error):
        """Make next calls to upload raise the provided exception"""
        self._upload_remote_error = error

    def make_server_call_raise(self, error):
        """Make next calls to the server raise the provided exception"""
        self._server_error = error
