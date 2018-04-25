# coding: utf-8
from nxdrive.client.remote_filtered_file_system_client import \
    RemoteFileSystemClient


class RemoteTestClient(RemoteFileSystemClient):

    _download_remote_error = None
    _upload_remote_error = None
    _server_error = None
    raise_on = None

    def __init__(self, *args, **kwargs):
        super(RemoteTestClient, self).__init__(*args, **kwargs)
        self.operations.execute = self.execute

    def download(self, *args, **kwargs):
        self._raise(self._download_remote_error, *args, **kwargs)
        return super(RemoteTestClient, self).download(*args, **kwargs)

    def upload(self, *args, **kwargs):
        self._raise(self._upload_remote_error, *args, **kwargs)
        return super(RemoteTestClient, self).upload(*args, **kwargs)

    def execute(self, *args, **kwargs):
        self._raise(self._server_error, *args, **kwargs)
        return self.operations.execute(*args, **kwargs)

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
