'''
Created on 23 juin 2014

@author: Remi Cattiau
'''
from nxdrive.client.remote_filtered_file_system_client import RemoteFileSystemClient
from nxdrive.client.common import DEFAULT_REPOSITORY_NAME


class RemoteTestClient(RemoteFileSystemClient):

    _download_remote_error = None
    _upload_remote_error = None
    _server_error = None
    raise_on = None

    def __init__(self, server_url, user_id, device_id, client_version,
                 session, proxies=None, proxy_exceptions=None,
                 password=None, token=None, repository=DEFAULT_REPOSITORY_NAME,
                 ignored_prefixes=None, ignored_suffixes=None,
                 timeout=20, blob_timeout=None, cookie_jar=None,
                 upload_tmp_dir=None, check_suspended=None):
        super(RemoteTestClient, self).__init__(
            server_url, user_id, device_id,
            client_version, proxies, proxy_exceptions,
            password, token, repository, ignored_prefixes,
            ignored_suffixes, timeout, blob_timeout, cookie_jar,
            upload_tmp_dir, check_suspended)

    def do_get(self, *args, **kwargs):
        self._raise(self._download_remote_error, *args, **kwargs)
        return super(RemoteTestClient, self).do_get(*args, **kwargs)

    def upload(self, *args, **kwargs):
        self._raise(self._upload_remote_error, *args, **kwargs)
        return super(RemoteTestClient, self).upload(*args, **kwargs)

    def fetch_api(self):
        self._raise(self._server_error)
        return super(RemoteTestClient, self).fetch_api()

    def execute(self, *args, **kwargs):
        self._raise(self._server_error, *args, **kwargs)
        return super(RemoteTestClient, self).execute(*args, **kwargs)

    def make_download_raise(self, error):
        """ Make next calls to do_get() raise the provided exception. """
        self._download_remote_error = error

    def make_upload_raise(self, error):
        """ Make next calls to upload() raise the provided exception. """
        self._upload_remote_error = error

    def make_server_call_raise(self, error):
        """ Make next calls to the server raise the provided exception. """
        self._server_error = error

    def _raise(self, exc, *args, **kwargs):
        """ Make the next calls raise `exc` if `raise_on()` allowed it. """

        if exc:
            if not callable(self.raise_on):
                raise exc
            if self.raise_on(*args, **kwargs):
                raise exc

    def reset_errors(self):
        """ Remove custom errors. """

        self._download_remote_error = None
        self._upload_remote_error = None
        self._server_error = None
        self.raise_on = None
