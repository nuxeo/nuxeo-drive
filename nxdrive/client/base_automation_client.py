# coding: utf-8
""" Common Nuxeo Automation client utilities. """

import os
import random
import socket
import sys
import tempfile
import time
import urllib2
from logging import getLogger
from urllib2 import ProxyHandler
from urlparse import urlparse

from nuxeo.auth import TokenAuth
from nuxeo.client import Nuxeo
from nuxeo.exceptions import HTTPError
from nuxeo.models import Batch, FileBlob
from poster.streaminghttp import get_handlers

from .common import BaseClient, FILE_BUFFER_SIZE
from ..engine.activity import Action, FileAction
from ..options import Options
from ..utils import (TOKEN_PERMISSION, get_device)

log = getLogger(__name__)

CHANGE_SUMMARY_OPERATION = 'NuxeoDrive.GetChangeSummary'
DEFAULT_NUXEO_TX_TIMEOUT = 300

DOWNLOAD_TMP_FILE_PREFIX = '.'
DOWNLOAD_TMP_FILE_SUFFIX = '.nxpart'

# 1s audit time resolution because of the datetime resolution of MYSQL
AUDIT_CHANGE_FINDER_TIME_RESOLUTION = 1.0

socket.setdefaulttimeout(DEFAULT_NUXEO_TX_TIMEOUT)


class InvalidBatchException(Exception):
    pass


def get_proxies_for_handler(proxy_settings):
    """Return a pair containing proxy string and exceptions list"""
    if proxy_settings.config == 'None':
        # No proxy, return an empty dictionary to disable
        # default proxy detection
        return {}, None
    elif proxy_settings.config == 'System':
        # System proxy, return None to use default proxy detection
        return None, None
    else:
        # Manual proxy settings, build proxy string and exceptions list
        if proxy_settings.authenticated:
            proxy_string = '%s:%s@%s:%s' % (proxy_settings.username,
                                            proxy_settings.password,
                                            proxy_settings.server,
                                            proxy_settings.port)
        else:
            proxy_string = '%s:%s' % (proxy_settings.server,
                                      proxy_settings.port)
        if proxy_settings.proxy_type is None:
            proxies = {'http': proxy_string, 'https': proxy_string}
        else:
            proxies = {proxy_settings.proxy_type: ('%s://%s' % (proxy_settings.proxy_type, proxy_string))}
        if proxy_settings.exceptions and proxy_settings.exceptions.strip():
            proxy_exceptions = [e.strip() for e in
                                proxy_settings.exceptions.split(',')]
        else:
            proxy_exceptions = None
        return proxies, proxy_exceptions


def get_proxy_config(proxies):
    if proxies is None:
        return 'System'
    elif proxies == {}:
        return 'None'
    return 'Manual'


def get_proxy_handler(proxies, proxy_exceptions=None, url=None):
    if proxies is None:
        # No proxies specified, use default proxy detection
        return urllib2.ProxyHandler()
    else:
        # Use specified proxies (can be empty to disable default detection)
        if proxies:
            if proxy_exceptions is not None and url is not None:
                hostname = urlparse(url).hostname
                for exception in proxy_exceptions:
                    if exception == hostname:
                        # Server URL is in proxy exceptions,
                        # don't use any proxy
                        proxies = {}
        return urllib2.ProxyHandler(proxies)


def get_opener_proxies(opener):
    for handler in opener.handlers:
        if isinstance(handler, ProxyHandler):
            return handler.proxies
    return None


class AddonNotInstalled(Exception):
    pass


class NewUploadAPINotAvailable(Exception):
    pass


class BaseAutomationClient(BaseClient):
    """Client for the Nuxeo Content Automation HTTP API

    timeout is a short timeout to avoid having calls to fast JSON operations
    to block and freeze the application in case of network issues.

    blob_timeout is long (or infinite) timeout dedicated to long HTTP
    requests involving a blob transfer.

    Supports HTTP proxies.
    If proxies is given, it must be a dictionary mapping protocol names to
    URLs of proxies.
    If proxies is None, uses default proxy detection:
    read the list of proxies from the environment variables <PROTOCOL>_PROXY;
    if no proxy environment variables are set, then in a Windows environment
    proxy settings are obtained from the registry's Internet Settings section,
    and in a Mac OS X environment proxy information is retrieved from the
    OS X System Configuration Framework.
    To disable autodetected proxy pass an empty dictionary.
    """
    # TODO: handle system proxy detection under Linux,
    # see https://jira.nuxeo.com/browse/NXP-12068

    # Parameters used when negotiating authentication token:
    application_name = 'Nuxeo Drive'

    __operations = None

    def __init__(self, server_url, user_id, device_id, client_version,
                 dao=None, proxies=None, proxy_exceptions=None,
                 password=None, token=None, repository=Options.remote_repo,
                 timeout=20, blob_timeout=60, cookie_jar=None,
                 upload_tmp_dir=None, check_suspended=None):
        # Function to check during long-running processing like upload /
        # download if the synchronization thread needs to be suspended
        self.check_suspended = check_suspended

        if dao:
            self._dao = dao

        if timeout is None or timeout < 0:
            timeout = 20
        self.timeout = timeout
        # Dont allow null timeout
        if blob_timeout is None or blob_timeout < 0:
            blob_timeout = 60
        self.blob_timeout = blob_timeout

        self.upload_tmp_dir = (upload_tmp_dir if upload_tmp_dir is not None
                               else tempfile.gettempdir())

        self.user_id = user_id
        self.device_id = device_id
        self.client_version = client_version
        self.server_url = server_url
        self.repository = repository

        self.client = Nuxeo(host=server_url, app_name=self.application_name,
                            version=client_version, repository=repository,
                            cookie_jar=cookie_jar, proxies=proxies)

        self.client.unlock_path = self.unlock_path
        self.client.lock_path = self.lock_path
        self.client.check_suspended = check_suspended
        self._update_auth(password=password, token=token)

        self.cookie_jar = cookie_jar
        cookie_processor = urllib2.HTTPCookieProcessor(
            cookiejar=cookie_jar)

        # Get proxy handler
        proxy_handler = get_proxy_handler(proxies,
                                          proxy_exceptions=proxy_exceptions,
                                          url=server_url)

        # Build URL openers
        self.opener = urllib2.build_opener(cookie_processor, proxy_handler)
        self.streaming_opener = urllib2.build_opener(cookie_processor,
                                                     proxy_handler,
                                                     *get_handlers())

        # Set Proxy flag
        self.is_proxy = False
        opener_proxies = get_opener_proxies(self.opener)
        log.trace('Proxy configuration: %s, effective proxy list: %r', get_proxy_config(proxies), opener_proxies)
        if opener_proxies:
            self.is_proxy = True

        self.automation_url = server_url + 'site/automation/'
        self.batch_upload_url = 'batch/upload'
        self.batch_execute_url = 'batch/execute'

        # New batch upload API
        self.new_upload_api_available = True
        self.rest_api_url = server_url + 'api/v1/'
        self.batch_upload_path = 'upload'
        self.is_event_log_id = True

        self.check_access()

    def __repr__(self):
        attrs = ', '.join('{}={!r}'.format(attr, getattr(self, attr, None))
                          for attr in sorted(self.__init__.__code__.co_varnames[1:]))
        return '<{} {}>'.format(self.__class__.__name__, attrs)

    @property
    def operations(self):
        """
        A dict of all operations and their parameters.
        Fetched on demand as it is a heavy work for the server and the network.

        :rtype: dict
        """

        if not self.__operations:
            self.fetch_api()
        return self.__operations

    def check_access(self):
        """ Simple call to check credentials. """
        self.client.client.request('GET', 'site/automation/logInAudit',
            headers=self._get_common_headers())

    def fetch_api(self):
        self.__operations = self.client.operations.operations

        # Is event log id available in change summary?
        # See https://jira.nuxeo.com/browse/NXP-14826
        change_summary_op = self._check_operation(CHANGE_SUMMARY_OPERATION)
        self.is_event_log_id = 'lowerBound' in [
                        param['name'] for param in change_summary_op['params']]

    def execute(self, command, url=None, op_input=None, timeout=-1,
                check_params=False, void_op=False, extra_headers=None,
                enrichers=None, file_out=None, **params):
        """Execute an Automation operation"""
        headers = extra_headers or {}
        if self.repository != 'default':
            headers.update({'X-NXRepository': self.repository})
        if enrichers:
            headers.update({
                'X-NXenrichers.document': ', '.join(enrichers),
            })

        timeout = self.timeout if timeout == -1 else timeout

        return self.client.operations.execute(
            command=command, input_obj=op_input, check_params=check_params,
            void_op=void_op, headers=headers, file_out=file_out,
            timeout=timeout, **params)

    def execute_with_blob_streaming(self, command, file_path, filename=None,
                                    mime_type=None, **params):
        """Execute an Automation operation using a batch upload as an input

        Upload is streamed.
        """
        tick = time.time()
        action = FileAction('Upload', file_path, filename)
        try:
            batch = None
            if self.is_new_upload_api_available():
                try:
                    # Init resumable upload getting a batch generated by the
                    # server. This batch is to be used as a resumable session
                    batch = self.init_upload()
                except NewUploadAPINotAvailable:
                    log.debug('New upload API is not available on server %s',
                              self.server_url)
                    self.new_upload_api_available = False
            if batch is None:
                # New upload API is not available, generate a batch id
                batch = Batch(batchId=self._generate_unique_id())
                batch.service = self.client.uploads

            blob = FileBlob(file_path)
            if filename:
                blob.name = filename
            if mime_type:
                blob.mimetype = mime_type
            upload_result = batch.upload(blob)

            upload_duration = int(time.time() - tick)
            action.transfer_duration = upload_duration
            # Use upload duration * 2 as Nuxeo transaction timeout
            tx_timeout = max(DEFAULT_NUXEO_TX_TIMEOUT, upload_duration * 2)
            log.trace('Using %d seconds [max(%d, 2 * upload time=%d)] as Nuxeo'
                      ' transaction timeout for batch execution of %s'
                      ' with file %s', tx_timeout, DEFAULT_NUXEO_TX_TIMEOUT,
                      upload_duration, command, file_path)
            if upload_duration > 0:
                log.trace('Speed for %d o is %d s : %f o/s',
                          os.stat(file_path).st_size, upload_duration,
                          os.stat(file_path).st_size / upload_duration)
            # NXDRIVE-433: Compat with 7.4 intermediate state
            self.new_upload_api_available = upload_result.uploaded is not None
            if upload_result.batch_id is not None:
                return self.execute_batch(command, upload_result,
                                          tx_timeout, **params)
            else:
                raise ValueError("Bad response from batch upload with id '%s' "
                                 "and file path '%s'" % (batch.uid,
                                                         file_path))
        except InvalidBatchException:
            self.cookie_jar.clear_session_cookies()
        finally:
            self.end_action()

    @staticmethod
    def get_upload_buffer(input_file):
        if sys.platform != 'win32':
            return os.fstatvfs(input_file.fileno()).f_bsize
        return FILE_BUFFER_SIZE

    def init_upload(self):
        try:
            return self.client.uploads.batch()
        except HTTPError as e:
            if e.status == 404:
                raise NewUploadAPINotAvailable()
            if e.status == 500:
                not_found_exceptions = [
                    'com.sun.jersey.api.NotFoundException',
                    'org.nuxeo.ecm.webengine.model.TypeNotFoundException']
                for exception in not_found_exceptions:
                    if exception in e.stacktrace or exception in e.message:
                        raise NewUploadAPINotAvailable()
            raise e

    def server_reachable(self):
        """
        Simple call to the server status page to check if it is reachable.
        """
        return self.client.client.is_reachable()

    def upload(self, batch_id, file_path, filename=None, file_index=0,
               mime_type=None):
        """Upload a file through an Automation batch

        Uses poster.httpstreaming to stream the upload
        and not load the whole file in memory.
        """
        FileAction('Upload', file_path, filename)

        blob = FileBlob(file_path)
        batch = Batch(batchId=batch_id)
        batch.service = self.client.uploads

        resp = batch.upload(blob)
        self.end_action()

        return resp

    @staticmethod
    def end_action():
        Action.finish_action()

    def execute_batch(self, command, blob, tx_timeout, **params):
        """Execute a file upload Automation batch"""
        extra_headers = {'Nuxeo-Transaction-Timeout': str(tx_timeout), }
        if self.is_new_upload_api_available():
            return self.execute(
                command, timeout=tx_timeout, op_input=blob,
                check_params=False, extra_headers=extra_headers, **params)
        else:
            raise NotImplementedError()
            return self.execute(self.batch_execute_url, timeout=tx_timeout,
                                operationId=command, batchId=blob.batch_id,
                                fileIdx=blob.fileIdx, check_params=False,
                                extra_headers=extra_headers, **params)

    def is_event_log_id_available(self):
        return self.is_event_log_id

    def is_elasticsearch_audit(self):
        return 'NuxeoDrive.WaitForElasticsearchCompletion' in self.operations

    def is_nuxeo_drive_attach_blob(self):
        return 'NuxeoDrive.AttachBlob' in self.operations

    def is_new_upload_api_available(self):
        return self.new_upload_api_available

    def request_token(self, revoke=False):
        """Request and return a new token for the user"""
        return self.client.client.request_auth_token(
            device_id=self.device_id, app_name=self.application_name,
            permission=TOKEN_PERMISSION, device=get_device(), revoke=revoke)

    def revoke_token(self):
        self.request_token(revoke=True)

    def wait(self):
        # Used for tests
        if self.is_elasticsearch_audit():
            self.execute('NuxeoDrive.WaitForElasticsearchCompletion')
        else:
            # Backward compatibility with JPA audit implementation,
            # in which case we are also backward compatible
            # with date based resolution
            if not self.is_event_log_id_available():
                time.sleep(AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
            self.execute('NuxeoDrive.WaitForAsyncCompletion')

    def make_tmp_file(self, content):
        """Create a temporary file with the given content
        for streaming upload purposes.

        Make sure that you remove the temporary file with os.remove()
        when done with it.
        """
        fd, path = tempfile.mkstemp(suffix=u'-nxdrive-file-to-upload',
                                    dir=self.upload_tmp_dir)
        with open(path, 'wb') as f:
            f.write(content)
        os.close(fd)
        return path

    def _update_auth(self, password=None, token=None):
        """Select the most appropriate auth headers based on credentials"""
        if token:
            self.client.client.auth = TokenAuth(token)
        elif password:
            self.client.client.auth = (self.user_id, password)
        else:
            raise ValueError('Either password or token must be provided')

    def _get_common_headers(self):
        """
        Headers to include in every HTTP requests

        Includes the authentication heads (token based or basic auth if no
        token).

        Also include an application name header to make it possible for the
        server to compute access statistics for various client types (e.g.
        browser vs devices).
        """
        return {
            'X-User-Id': self.user_id,
            'X-Device-Id': self.device_id,
            'X-Client-Version': self.client_version,
            'User-Agent': self.application_name + '/' + self.client_version,
            'X-Application-Name': self.application_name,
            'Cache-Control': 'no-cache',
        }

    def _get_cookies(self):
        return list(self.cookie_jar) if self.cookie_jar is not None else []

    def _check_operation(self, command):
        if command not in self.operations:
            if command.startswith('NuxeoDrive.'):
                raise AddonNotInstalled(
                    'Either nuxeo-drive addon is not installed on server %s '
                    'or server version is lighter than the minimum version '
                    'compatible with the client version %s, in which case '
                    'a downgrade of Nuxeo Drive is needed.' % (
                        self.server_url, self.client_version))
            else:
                raise ValueError("'%s' is not a registered operations."
                                 % command)
        return self.operations[command]

        # TODO: add typechecking

    @staticmethod
    def _generate_unique_id():
        """Generate a unique id based on a timestamp and a random integer"""

        return str(time.time()) + '_' + str(random.randint(0, 1000000000))

    def download(self, url, file_out=None, digest=None):
        log.trace('Downloading file from %r to %r with digest=%s',
                  url, file_out, digest)

        resp = self.client.client.request(
            'GET', url.replace(self.server_url, ''))

        current_action = Action.get_current_action()
        if current_action and resp:
            current_action.size = int(resp.headers.get('Content-Length', 0))

        if file_out:
            locker = self.unlock_path(file_out)
            try:
                self.client.operations.save_to_file(
                    current_action, resp, file_out, digest=digest,
                    chunk_size=FILE_BUFFER_SIZE)
            finally:
                self.lock_path(file_out, locker)
            return file_out
        else:
            result = resp.content
            return result
