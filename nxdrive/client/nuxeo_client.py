# coding: utf-8
import os
import socket
import tempfile
import time
from logging import getLogger
from threading import Lock

from nuxeo.auth import TokenAuth
from nuxeo.client import Nuxeo
from nuxeo.models import FileBlob

from ..constants import (APP_NAME, BLOB_TIMEOUT, FILE_BUFFER_SIZE, TIMEOUT,
                         TOKEN_PERMISSION, TX_TIMEOUT)
from ..engine.activity import Action, FileAction
from ..options import Options
from ..utils import get_device, lock_path, unlock_path

log = getLogger(__name__)

socket.setdefaulttimeout(TX_TIMEOUT)


class BaseNuxeo(Nuxeo):
    def __init__(
            self,
            url,  # type: Text
            user_id,  # type: Text
            device_id,  # type: Text
            version,  # type: Text
            dao=None,  # type: Any
            proxies=None,  # type: Dict
            proxy_exceptions=None,  # type: Array
            password=None,  # type: Text
            token=None,  # type: Text
            repository=Options.remote_repo,  # type: Text
            timeout=TIMEOUT,  # type: int
            blob_timeout=BLOB_TIMEOUT,  # type: int
            cookie_jar=None,
            upload_tmp_dir=None,  # type: Text
            check_suspended=None,  # type: Callable
            **kwargs  # type: Any
    ):
        auth = TokenAuth(token) if token else (user_id, password)
        super(BaseNuxeo, self).__init__(
            auth=auth, host=url, app_name=APP_NAME,
            version=version, proxies=proxies, repository=repository,
            cookie_jar=cookie_jar, **kwargs)

        self.client.headers.update({
            'X-User-Id': user_id,
            'X-Device-Id': device_id,
            'Cache-Control': 'no-cache'
        })

        if dao:
            self._dao = dao

        self.timeout = timeout if timeout > 0 else TIMEOUT
        self.blob_timeout = blob_timeout if blob_timeout > 0 else BLOB_TIMEOUT

        self.device_id = device_id
        self.user_id = user_id
        self.version = version
        self.check_suspended = check_suspended

        self.upload_tmp_dir = (upload_tmp_dir if upload_tmp_dir is not None
                               else tempfile.gettempdir())
        self.upload_lock = Lock()

        self.check_access()

    def __repr__(self):
        attrs = sorted(self.__init__.__code__.co_varnames[1:])
        attrs = ', '.join('{}={!r}'.format(attr, getattr(self, attr, None))
                          for attr in attrs)
        return '<{} {}>'.format(self.__class__.__name__, attrs)

    def check_access(self):
        """ Simple call to check credentials. """
        self.client.request('GET', 'site/automation/logInAudit')

    def is_elasticsearch_audit(self):
        return ('NuxeoDrive.WaitForElasticsearchCompletion'
                in self.operations.operations)

    def is_nuxeo_drive_attach_blob(self):
        return 'NuxeoDrive.AttachBlob' in self.operations.operations

    def request_token(self, revoke=False):
        """Request and return a new token for the user"""
        return self.client.request_auth_token(
            device_id=self.device_id, app_name=APP_NAME,
            permission=TOKEN_PERMISSION, device=get_device(), revoke=revoke)

    def revoke_token(self):
        self.request_token(revoke=True)

    def wait(self):
        # Used for tests
        if self.is_elasticsearch_audit():
            self.operations.execute(
                command='NuxeoDrive.WaitForElasticsearchCompletion')
        else:
            # Backward compatibility with JPA audit implementation,
            # in which case we are also backward compatible
            # with date based resolution
            self.operations.execute(
                command='NuxeoDrive.WaitForAsyncCompletion')

    def download(self, url, file_out=None, digest=None):
        log.trace('Downloading file from %r to %r with digest=%s',
                  url, file_out, digest)

        resp = self.client.request(
            'GET', url.replace(self.client.host, ''))

        current_action = Action.get_current_action()
        if current_action and resp:
            current_action.size = int(resp.headers.get('Content-Length', 0))

        if file_out:
            locker = unlock_path(file_out)
            try:
                self.operations.save_to_file(
                    current_action, resp, file_out, digest=digest,
                    chunk_size=FILE_BUFFER_SIZE)
            finally:
                lock_path(file_out, locker)
            return file_out
        else:
            result = resp.content
            return result

    def upload(self, file_path, filename=None, mime_type=None, command=None,
               **params):
        """ Upload a file with a batch.

        If command is not None, the operation is executed
        with the batch as an input.
        """
        with self.upload_lock:
            tick = time.time()
            action = FileAction('Upload', file_path, filename)
            try:
                # Init resumable upload getting a batch generated by the
                # server. This batch is to be used as a resumable session
                batch = self.uploads.batch()

                blob = FileBlob(file_path)
                if filename:
                    blob.name = filename
                if mime_type:
                    blob.mimetype = mime_type
                upload_result = batch.upload(blob)

                upload_duration = int(time.time() - tick)
                action.transfer_duration = upload_duration
                # Use upload duration * 2 as Nuxeo transaction timeout
                tx_timeout = max(TX_TIMEOUT, upload_duration * 2)
                log.trace(
                    'Using %d seconds [max(%d, 2 * upload time=%d)] as '
                    'Nuxeo transaction timeout for batch execution of %s '
                    'with file %s', tx_timeout, TX_TIMEOUT, upload_duration,
                    command, file_path)

                if upload_duration > 0:
                    log.trace('Speed for %d o is %d s : %f o/s',
                              os.stat(file_path).st_size, upload_duration,
                              os.stat(file_path).st_size / upload_duration)

                if command:
                    headers = {'Nuxeo-Transaction-Timeout': str(tx_timeout)}
                    return self.operations.execute(
                        command=command, timeout=tx_timeout,
                        input_obj=upload_result, check_params=False,
                        headers=headers, **params)
            finally:
                FileAction.finish_action()
