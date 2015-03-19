"""Common Nuxeo Automation client utilities."""

import sys
import base64
import json
import urllib2
import random
import time
import os
import tempfile
from urllib import urlencode
from poster.streaminghttp import get_handlers
from nxdrive.logging_config import get_logger
from nxdrive.client.common import BaseClient
from nxdrive.client.common import DEFAULT_REPOSITORY_NAME
from nxdrive.client.common import FILE_BUFFER_SIZE
from nxdrive.client.common import DEFAULT_IGNORED_PREFIXES
from nxdrive.client.common import DEFAULT_IGNORED_SUFFIXES
from nxdrive.client.common import safe_filename
from nxdrive.engine.activity import Action, FileAction
from nxdrive.utils import guess_mime_type
from nxdrive.utils import force_decode
from urllib2 import ProxyHandler
from urlparse import urlparse
import socket


log = get_logger(__name__)

DEVICE_DESCRIPTIONS = {
    'linux2': 'Linux Desktop',
    'darwin': 'Mac OSX Desktop',
    'cygwin': 'Windows Desktop',
    'win32': 'Windows Desktop',
}
CHANGE_SUMMARY_OPERATION = 'NuxeoDrive.GetChangeSummary'
DEFAULT_NUXEO_TX_TIMEOUT = 300

DOWNLOAD_TMP_FILE_PREFIX = '.'
DOWNLOAD_TMP_FILE_SUFFIX = '.nxpart'

socket.setdefaulttimeout(DEFAULT_NUXEO_TX_TIMEOUT)


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
            proxy_string = ("%s://%s:%s@%s:%s") % (
                                proxy_settings.proxy_type,
                                proxy_settings.username,
                                proxy_settings.password,
                                proxy_settings.server,
                                proxy_settings.port)
        else:
            proxy_string = ("%s://%s:%s") % (
                                proxy_settings.proxy_type,
                                proxy_settings.server,
                                proxy_settings.port)
        proxies = {proxy_settings.proxy_type: proxy_string}
        if proxy_settings.exceptions and proxy_settings.exceptions.strip():
            proxy_exceptions = [e.strip() for e in
                                proxy_settings.exceptions.split(',')]
        else:
            proxy_exceptions = None
        return proxies, proxy_exceptions


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


class AddonNotInstalled(Exception):
    pass


class Unauthorized(Exception):

    def __init__(self, server_url, user_id, code=403):
        self.server_url = server_url
        self.user_id = user_id
        self.code = code

    def __str__(self):
        return ("'%s' is not authorized to access '%s' with"
                " the provided credentials" % (self.user_id, self.server_url))


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

    # Used for testing network errors
    _remote_error = None

    # Used for testing local device errors when downloading a file
    _local_error = None

    # Parameters used when negotiating authentication token:
    application_name = 'Nuxeo Drive'

    permission = 'ReadWrite'

    def __init__(self, server_url, user_id, device_id, client_version,
                 proxies=None, proxy_exceptions=None,
                 password=None, token=None, repository=DEFAULT_REPOSITORY_NAME,
                 ignored_prefixes=None, ignored_suffixes=None,
                 timeout=20, blob_timeout=None, cookie_jar=None,
                 upload_tmp_dir=None, check_suspended=None):

        # Function to check during long-running processing like upload /
        # download if the synchronization thread needs to be suspended
        self.check_suspended = check_suspended

        self.timeout = timeout
        self.blob_timeout = blob_timeout
        if ignored_prefixes is not None:
            self.ignored_prefixes = ignored_prefixes
        else:
            self.ignored_prefixes = DEFAULT_IGNORED_PREFIXES

        if ignored_suffixes is not None:
            self.ignored_suffixes = ignored_suffixes
        else:
            self.ignored_suffixes = DEFAULT_IGNORED_SUFFIXES

        self.upload_tmp_dir = (upload_tmp_dir if upload_tmp_dir is not None
                               else tempfile.gettempdir())

        if not server_url.endswith('/'):
            server_url += '/'
        self.server_url = server_url

        self.repository = repository

        self.user_id = user_id
        self.device_id = device_id
        self.client_version = client_version
        self._update_auth(password=password, token=token)

        self.cookie_jar = cookie_jar
        cookie_processor = urllib2.HTTPCookieProcessor(
            cookiejar=cookie_jar)

        # Get proxy handler
        proxy_handler = get_proxy_handler(proxies,
                                          proxy_exceptions=proxy_exceptions,
                                          url=self.server_url)

        # Build URL openers
        self.opener = urllib2.build_opener(cookie_processor, proxy_handler)
        self.streaming_opener = urllib2.build_opener(cookie_processor,
                                                     proxy_handler,
                                                     *get_handlers())

        # Set Proxy flag
        self.is_proxy = False
        for handler in self.opener.handlers:
            if isinstance(handler, ProxyHandler):
                if handler.proxies:
                    self.is_proxy = True

        self.automation_url = server_url + 'site/automation/'
        self.batch_upload_url = 'batch/upload'
        self.batch_execute_url = 'batch/execute'

        self.fetch_api()

    def make_remote_raise(self, error):
        """Make next calls to server raise the provided exception"""
        self._remote_error = error

    def make_local_raise(self, error):
        """Make do_get raise the provided exception"""
        self._local_error = error

    def fetch_api(self):
        base_error_message = (
            "Failed to connect to Nuxeo server %s"
        ) % (self.server_url)
        url = self.automation_url
        headers = self._get_common_headers()
        cookies = self._get_cookies()
        log.trace("Calling %s with headers %r and cookies %r",
            url, headers, cookies)
        req = urllib2.Request(url, headers=headers)
        try:
            response = json.loads(self.opener.open(
                req, timeout=self.timeout).read())
        except urllib2.HTTPError as e:
            if e.code == 401 or e.code == 403:
                raise Unauthorized(self.server_url, self.user_id, e.code)
            else:
                msg = base_error_message + "\nHTTP error %d" % e.code
                if hasattr(e, 'msg'):
                    msg = msg + ": " + e.msg
                e.msg = msg
                raise e
        except urllib2.URLError as e:
            msg = base_error_message
            if hasattr(e, 'message') and e.message:
                msg = msg + force_decode(": " + e.message)
            elif hasattr(e, 'reason') and e.reason:
                if (hasattr(e.reason, 'message')
                    and e.reason.message):
                    msg = msg + force_decode(": " + e.reason.message)
                elif (hasattr(e.reason, 'strerror')
                    and e.reason.strerror):
                    msg = msg + force_decode(": " + e.reason.strerror)
            if self.is_proxy:
                msg = (msg + "\nPlease check your Internet connection,"
                       + " make sure the Nuxeo server URL is valid"
                       + " and check the proxy settings.")
            else:
                msg = (msg + "\nPlease check your Internet connection"
                       + " and make sure the Nuxeo server URL is valid.")
            e.msg = msg
            raise e
        except Exception as e:
            msg = base_error_message
            if hasattr(e, 'msg'):
                msg = msg + ": " + e.msg
            e.msg = msg
            raise e
        self.operations = {}
        for operation in response["operations"]:
            self.operations[operation['id']] = operation
            op_aliases = operation.get('aliases')
            if op_aliases:
                for op_alias in op_aliases:
                    self.operations[op_alias] = operation

        # Is event log id available in change summary?
        # See https://jira.nuxeo.com/browse/NXP-14826
        change_summary_op = self._check_operation(CHANGE_SUMMARY_OPERATION)
        self.is_event_log_id = 'lowerBound' in [
                        param['name'] for param in change_summary_op['params']]

    def execute(self, command, op_input=None, timeout=-1,
                check_params=True, void_op=False, extra_headers=None,
                file_out=None, **params):
        """Execute an Automation operation"""
        if self._remote_error is not None:
            # Simulate a configurable (e.g. network or server) error for the
            # tests
            raise self._remote_error
        if check_params:
            self._check_params(command, params)

        url = self.automation_url + command
        headers = {
            "Content-Type": "application/json+nxrequest",
            "Accept": "application/json+nxentity, */*",
            "X-NXproperties": "*",
            # Keep compatibility with old header name
            "X-NXDocumentProperties": "*",
        }
        if void_op:
            headers.update({"X-NXVoidOperation": "true"})
        if self.repository != DEFAULT_REPOSITORY_NAME:
            headers.update({"X-NXRepository": self.repository})
        if extra_headers is not None:
            headers.update(extra_headers)
        headers.update(self._get_common_headers())

        json_struct = {'params': {}}
        for k, v in params.items():
            if v is None:
                continue
            if k == 'properties':
                s = ""
                for propname, propvalue in v.items():
                    s += "%s=%s\n" % (propname, propvalue)
                json_struct['params'][k] = s.strip()
            else:
                json_struct['params'][k] = v
        if op_input:
            json_struct['input'] = op_input
        log.trace("Dumping JSON structure: %s", json_struct)
        data = json.dumps(json_struct)

        cookies = self._get_cookies()
        log.trace("Calling %s with headers %r, cookies %r"
                  " and JSON payload %r",
            url, headers, cookies,  data)
        req = urllib2.Request(url, data, headers)
        timeout = self.timeout if timeout == -1 else timeout
        try:
            resp = self.opener.open(req, timeout=timeout)
        except Exception as e:
            self._log_details(e)
            raise
        current_action = Action.get_current_action()
        if file_out is not None:
            locker = self.unlock_path(file_out)
            try:
                with open(file_out, "wb") as f:
                    while True:
                        # Check if synchronization thread was suspended
                        if self.check_suspended is not None:
                            self.check_suspended('File download: %s'
                                                 % file_out)
                        buffer_ = resp.read(self.get_download_buffer())
                        if buffer_ == '':
                            break
                        if current_action:
                            current_action.progress += (
                                                self.get_download_buffer())
                        f.write(buffer_)
                    if self._remote_error is not None:
                        # Simulate a configurable remote (e.g. network or
                        # server) error for the tests
                        raise self._remote_error
                    if self._local_error is not None:
                        # Simulate a configurable local error (e.g. "No
                        # space left on device") for the tests
                        raise self._local_error
                return None, file_out
            finally:
                self.lock_path(file_out, locker)
        else:
            return self._read_response(resp, url)

    def execute_with_blob_streaming(self, command, file_path, filename=None,
                                    mime_type=None, **params):
        """Execute an Automation operation using a batch upload as an input

        Upload is streamed.
        """
        batch_id = self._generate_unique_id()
        tick = time.time()
        upload_result = self.upload(batch_id, file_path, filename=filename,
                                    mime_type=mime_type)
        upload_duration = int(time.time() - tick)
        # Use upload duration * 2 as Nuxeo transaction timeout
        tx_timeout = max(DEFAULT_NUXEO_TX_TIMEOUT, upload_duration * 2)
        log.trace('Using %d seconds [max(%d, 2 * upload time=%d)] as Nuxeo'
                  ' transaction timeout for batch execution of %s'
                  ' with file %s', tx_timeout, DEFAULT_NUXEO_TX_TIMEOUT,
                  upload_duration, command, file_path)
        if upload_result['uploaded'] == 'true':
            FileAction("Upload", file_path, filename)
            result = self.execute_batch(command, batch_id, '0', tx_timeout,
                                      **params)
            self.end_action()
            return result
        else:
            raise ValueError("Bad response from batch upload with id '%s'"
                             " and file path '%s'" % (batch_id, file_path))

    def get_upload_buffer(self, input_file):
        if sys.platform != 'win32':
            return os.fstatvfs(input_file.fileno()).f_bsize
        else:
            return FILE_BUFFER_SIZE

    def upload(self, batch_id, file_path, filename=None, file_index=0,
               mime_type=None):
        """Upload a file through an Automation batch

        Uses poster.httpstreaming to stream the upload
        and not load the whole file in memory.
        """
        FileAction("Upload", file_path, filename)
        # Request URL
        url = self.automation_url.encode('ascii') + self.batch_upload_url

        # HTTP headers
        if filename is None:
            filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        if mime_type is None:
            mime_type = guess_mime_type(filename)
        # Quote UTF-8 filenames even though JAX-RS does not seem to be able
        # to retrieve them as per: https://tools.ietf.org/html/rfc5987
        filename = safe_filename(filename)
        quoted_filename = urllib2.quote(filename.encode('utf-8'))
        headers = {
            "X-Batch-Id": batch_id,
            "X-File-Idx": file_index,
            "X-File-Name": quoted_filename,
            "X-File-Size": file_size,
            "X-File-Type": mime_type,
            "Content-Type": "application/octet-stream",
            "Content-Length": file_size,
        }
        headers.update(self._get_common_headers())

        # Request data
        input_file = open(file_path, 'rb')
        # Use file system block size if available for streaming buffer
        fs_block_size = self.get_upload_buffer(input_file)
        log.trace("Using file system block size"
                  " for the streaming upload buffer: %u bytes", fs_block_size)
        data = self._read_data(input_file, fs_block_size)

        # Execute request
        cookies = self._get_cookies()
        log.trace("Calling %s with headers %r and cookies %r for file %s",
            url, headers, cookies, file_path)
        req = urllib2.Request(url, data, headers)
        try:
            resp = self.streaming_opener.open(req, timeout=self.blob_timeout)
        except Exception as e:
            self._log_details(e)
            raise
        finally:
            input_file.close()
        self.end_action()
        return self._read_response(resp, url)

    def end_action(self):
        Action.finish_action()

    def execute_batch(self, op_id, batch_id, file_idx, tx_timeout, **params):
        """Execute a file upload Automation batch"""
        extra_headers = {'Nuxeo-Transaction-Timeout': tx_timeout, }
        return self.execute(self.batch_execute_url, timeout=tx_timeout,
                     operationId=op_id, batchId=batch_id, fileIdx=file_idx,
                     check_params=False, extra_headers=extra_headers, **params)

    def is_addon_installed(self):
        return 'NuxeoDrive.GetRoots' in self.operations

    def is_event_log_id_available(self):
        return self.is_event_log_id

    def request_token(self, revoke=False):
        """Request and return a new token for the user"""
        base_error_message = (
            "Failed to connect to Nuxeo server %s with user %s"
            " to acquire a token"
        ) % (self.server_url, self.user_id)

        parameters = {
            'deviceId': self.device_id,
            'applicationName': self.application_name,
            'permission': self.permission,
            'revoke': 'true' if revoke else 'false',
        }
        device_description = DEVICE_DESCRIPTIONS.get(sys.platform)
        if device_description:
            parameters['deviceDescription'] = device_description
        url = self.server_url + 'authentication/token?'
        url += urlencode(parameters)

        headers = self._get_common_headers()
        cookies = self._get_cookies()
        log.trace("Calling %s with headers %r and cookies %r",
                url, headers, cookies)
        req = urllib2.Request(url, headers=headers)
        try:
            token = self.opener.open(req, timeout=self.timeout).read()
        except urllib2.HTTPError as e:
            if e.code == 401 or e.code == 403:
                raise Unauthorized(self.server_url, self.user_id, e.code)
            elif e.code == 404:
                # Token based auth is not supported by this server
                return None
            else:
                e.msg = base_error_message + ": HTTP error %d" % e.code
                raise e
        except Exception as e:
            if hasattr(e, 'msg'):
                e.msg = base_error_message + ": " + e.msg
            raise
        cookies = self._get_cookies()
        log.trace("Got token '%s' with cookies %r", token, cookies)
        # Use the (potentially re-newed) token from now on
        if not revoke:
            self._update_auth(token=token)
        return token

    def revoke_token(self):
        self.request_token(revoke=True)

    def wait(self):
        self.execute("NuxeoDrive.WaitForAsyncCompletion")

    def make_tmp_file(self, content):
        fd, path = tempfile.mkstemp(suffix=u'-nxdrive-file-to-upload',
                                   dir=self.upload_tmp_dir)
        with open(path, "wb") as f:
            f.write(content)
        os.close(fd)
        return path

    def _update_auth(self, password=None, token=None):
        """Select the most appropriate auth headers based on credentials"""
        if token is not None:
            self.auth = ('X-Authentication-Token', token)
        elif password is not None:
            basic_auth = 'Basic %s' % base64.b64encode(
                    self.user_id + ":" + password).strip()
            self.auth = ("Authorization", basic_auth)
        else:
            raise ValueError("Either password or token must be provided")

    def _get_common_headers(self):
        """Headers to include in every HTTP requests

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
            'User-Agent': self.application_name + "/" + self.client_version,
            'X-Application-Name': self.application_name,
            self.auth[0]: self.auth[1],
            'Cache-Control': 'no-cache',
        }

    def _get_cookies(self):
        return list(self.cookie_jar) if self.cookie_jar is not None else []

    def _check_operation(self, command):
        if command not in self.operations:
            if command.startswith('NuxeoDrive.'):
                raise AddonNotInstalled(
                    "Either nuxeo-drive addon is not installed on server %s or"
                    " server version is lighter than the minimum version"
                    " compatible with the client version %s, in which case a"
                    " downgrade of Nuxeo Drive is needed." % (
                        self.server_url, self.client_version))
            else:
                raise ValueError("'%s' is not a registered operations."
                                 % command)
        return self.operations[command]

    def _check_params(self, command, params):
        method = self._check_operation(command)
        required_params = []
        other_params = []
        for param in method['params']:
            if param['required']:
                required_params.append(param['name'])
            else:
                other_params.append(param['name'])

        for param in params.keys():
            if (not param in required_params
                and not param in other_params):
                log.trace("Unexpected param '%s' for operation '%s'", param,
                            command)
        for param in required_params:
            if not param in params:
                raise ValueError(
                    "Missing required param '%s' for operation '%s'" % (
                        param, command))

        # TODO: add typechecking

    def _read_response(self, response, url):
        info = response.info()
        s = response.read()
        content_type = info.get('content-type', '')
        cookies = self._get_cookies()
        if content_type.startswith("application/json"):
            log.trace("Response for '%s' with cookies %r: %r",
                url, cookies, s)
            return json.loads(s) if s else None
        else:
            log.trace("Response for '%s' with cookies %r has content-type %r",
                url, cookies, content_type)
            return s

    def _log_details(self, e):
        if hasattr(e, "fp"):
            detail = e.fp.read()
            try:
                exc = json.loads(detail)
                log.debug(exc['message'])
                log.debug(exc['stack'], exc_info=True)
            except:
                # Error message should always be a JSON message,
                # but sometimes it's not
                log.debug(detail)

    def _generate_unique_id(self):
        """Generate a unique id based on a timestamp and a random integer"""

        return str(time.time()) + '_' + str(random.randint(0, 1000000000))

    def _read_data(self, file_object, buffer_size):
        while True:
            current_action = Action.get_current_action()
            if current_action is not None and current_action.suspend:
                break
            # Check if synchronization thread was suspended
            if self.check_suspended is not None:
                self.check_suspended('File upload: %s' % file_object.name)
            r = file_object.read(buffer_size)
            if not r:
                break
            if current_action is not None:
                current_action.progress += buffer_size
            yield r

    def do_get(self, url, file_out=None):
        headers = self._get_common_headers()
        base_error_message = (
            "Failed to connect to Nuxeo server %r with user %r"
        ) % (self.server_url, self.user_id)
        try:
            log.trace("Calling '%s' with headers: %r", url, headers)
            req = urllib2.Request(url, headers=headers)
            response = self.opener.open(req, timeout=self.blob_timeout)
            current_action = Action.get_current_action()
            # Get the size file
            if (current_action and response is not None
                and response.info() is not None):
                current_action.size = int(response.info().getheader(
                                                    'Content-Length', 0))
            if file_out is not None:
                locker = self.unlock_path(file_out)
                try:
                    with open(file_out, "wb") as f:
                        while True:
                            # Check if synchronization thread was suspended
                            if self.check_suspended is not None:
                                self.check_suspended('File download: %s'
                                                     % file_out)
                            buffer_ = response.read(self.get_download_buffer())
                            if buffer_ == '':
                                break
                            if current_action:
                                current_action.progress += (
                                                    self.get_download_buffer())
                            f.write(buffer_)
                        if self._remote_error is not None:
                            # Simulate a configurable remote (e.g. network or
                            # server) error for the tests
                            raise self._remote_error
                        if self._local_error is not None:
                            # Simulate a configurable local error (e.g. "No
                            # space left on device") for the tests
                            raise self._local_error
                    return None, file_out
                finally:
                    self.lock_path(file_out, locker)
            else:
                return response.read(), None
        except urllib2.HTTPError as e:
            if e.code == 401 or e.code == 403:
                raise Unauthorized(self.server_url, self.user_id, e.code)
            else:
                e.msg = base_error_message + ": HTTP error %d" % e.code
                raise e
        except Exception as e:
            if hasattr(e, 'msg'):
                e.msg = base_error_message + ": " + e.msg
            raise

    def get_download_buffer(self):
        return FILE_BUFFER_SIZE
