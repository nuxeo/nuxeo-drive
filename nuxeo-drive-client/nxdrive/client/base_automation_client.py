"""Common Nuxeo Automation client utilities."""

import sys
import base64
import json
import urllib2
import mimetypes
import random
import time
import urllib
from urllib import urlencode
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from nxdrive.logging_config import get_logger
from nxdrive.client.common import DEFAULT_IGNORED_PREFIXES
from nxdrive.client.common import DEFAULT_IGNORED_SUFFIXES
from nxdrive.client.common import safe_filename


log = get_logger(__name__)


DEVICE_DESCRIPTIONS = {
    'linux2': 'Linux Desktop',
    'darwin': 'Mac OSX Desktop',
    'cygwin': 'Windows Desktop',
    'win32': 'Windows Desktop',
}


class Unauthorized(Exception):

    def __init__(self, server_url, user_id, code=403):
        self.server_url = server_url
        self.user_id = user_id
        self.code = code

    def __str__(self):
        return ("'%s' is not authorized to access '%s' with"
                " the provided credentials" % (self.user_id, self.server_url))


class BaseAutomationClient(object):
    """Client for the Nuxeo Content Automation HTTP API

    timeout is a short timeout to avoid having calls to fast JSON operations
    to block and freeze the application in case of network issues.

    blob_timeout is long (or infinite) timeout dedicated to long HTTP
    requests involving a blob transfer.

    """

    # Used for testing network errors
    _error = None

    # Parameters used when negotiating authentication token:
    application_name = 'Nuxeo Drive'

    permission = 'ReadWrite'

    def __init__(self, server_url, user_id, device_id,
                 password=None, token=None, repository="default",
                 ignored_prefixes=None, ignored_suffixes=None,
                 timeout=10, blob_timeout=None, cookie_jar=None):
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

        if not server_url.endswith('/'):
            server_url += '/'
        self.server_url = server_url

        # TODO: actually use the repository info in the requests
        self.repository = repository

        self.user_id = user_id
        self.device_id = device_id
        self._update_auth(password=password, token=token)

        self.cookie_jar = cookie_jar
        cookie_processor = urllib2.HTTPCookieProcessor(
            cookiejar=cookie_jar)
        self.opener = urllib2.build_opener(cookie_processor)
        self.automation_url = server_url + 'site/automation/'

        self.fetch_api()

    def make_raise(self, error):
        """Make next calls to server raise the provided exception"""
        self._error = error

    def fetch_api(self):
        headers = self._get_common_headers()
        base_error_message = (
            "Failed not connect to Nuxeo Content Automation on server %r"
            " with user %r"
        ) % (self.server_url, self.user_id)
        try:
            req = urllib2.Request(self.automation_url, headers=headers)
            response = json.loads(self.opener.open(
                req, timeout=self.timeout).read())
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
        self.operations = {}
        for operation in response["operations"]:
            self.operations[operation['id']] = operation

    def execute(self, command, input=None, timeout=-1, **params):
        if self._error is not None:
            # Simulate a configurable (e.g. network or server) error for the
            # tests
            raise self._error

        self._check_params(command, input, params)
        headers = {
            "Content-Type": "application/json+nxrequest",
            "X-NXDocumentProperties": "*",
        }
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

        if input:
            json_struct['input'] = input

        data = json.dumps(json_struct)
        cookies = list(self.cookie_jar) if self.cookie_jar is not None else []
        url = self.automation_url + command
        log.trace("Calling '%s' with cookies %r and json payload: %r",
            url, cookies,  data)
        req = urllib2.Request(url, data, headers)
        timeout = self.timeout if timeout == -1 else timeout
        try:
            resp = self.opener.open(req, timeout=timeout)
        except Exception, e:
            self._log_details(e)
            raise

        info = resp.info()
        s = resp.read()
        cookies = list(self.cookie_jar) if self.cookie_jar is not None else []
        content_type = info.get('content-type', '')
        if content_type.startswith("application/json"):
            log.trace(
                "Response for '%s' with cookies %r and json payload: %r",
                url, cookies, s)
            return json.loads(s) if s else None
        else:
            log.trace(
                "Response for '%s' with cookies %r  and with content-type: %r",
                url, cookies, content_type)
            return s

    def execute_with_blob(self, command, blob_content, filename, **params):
        self._check_params(command, None, params)

        container = MIMEMultipart("related",
                type="application/json+nxrequest",
                start="request")

        d = {'params': params}
        json_data = json.dumps(d)
        json_part = MIMEBase("application", "json+nxrequest")
        json_part.add_header("Content-ID", "request")
        json_part.set_payload(json_data)
        container.attach(json_part)

        ctype, encoding = mimetypes.guess_type(filename)
        if ctype:
            maintype, subtype = ctype.split('/', 1)
        else:
            maintype, subtype = "application", "octet-stream"
        blob_part = MIMEBase(maintype, subtype)
        blob_part.add_header("Content-ID", "input")
        blob_part.add_header("Content-Transfer-Encoding", "binary")

        # Quote UTF-8 filenames eventhough JAX-RS does not seem to be able
        # to retrieve them as per: https://tools.ietf.org/html/rfc5987
        filename = safe_filename(filename)
        quoted_filename = urllib.quote(filename.encode('utf-8'))
        content_disposition = ("attachment; filename*=UTF-8''%s"
                                % quoted_filename)
        blob_part.add_header("Content-Disposition", content_disposition)
        blob_part.set_payload(blob_content)
        container.attach(blob_part)

        # Create data by hand :(
        boundary = "====Part=%s=%s===" % (str(time.time()).replace('.', '='),
                                          random.randint(0, 1000000000))
        headers = {
            "Accept": "application/json+nxentity, */*",
            "Content-Type": ('multipart/related;boundary="%s";'
                             'type="application/json+nxrequest";'
                             'start="request"')
            % boundary,
        }
        headers.update(self._get_common_headers())

        # TODO: find a way to stream the parts without loading them all in
        # memory as a byte string

        # The code http://atlee.ca/software/poster/ might provide some
        # guidance to implement this although it cannot be reused directly
        # as we need tighter control on the headers of the multipart
        data = (
            "--%s\r\n"
            "%s\r\n"
            "--%s\r\n"
            "%s\r\n"
            "--%s--"
        ) % (
            boundary,
            json_part.as_string(),
            boundary,
            blob_part.as_string(),
            boundary,
        )
        url = self.automation_url.encode('ascii') + command
        cookies = list(self.cookie_jar) if self.cookie_jar is not None else []
        log.trace("Calling '%s' with cookies %r for file '%s'",
            url, cookies, filename)
        req = urllib2.Request(url, data, headers)
        try:
            resp = self.opener.open(req, timeout=self.blob_timeout)
        except Exception as e:
            self._log_details(e)
            raise

        info = resp.info()
        s = resp.read()

        content_type = info.get('content-type', '')
        cookies = list(self.cookie_jar) if self.cookie_jar is not None else []
        if content_type.startswith("application/json"):
            log.trace("Response for '%s' with cookies %r and json payload: %r",
                url, cookies, s)
            return json.loads(s) if s else None
        else:
            log.trace("Response for '%s' with cookies %r and content-type: %r",
                url, cookies, content_type)
            return s

    def is_addon_installed(self):
        return 'NuxeoDrive.GetRoots' in self.operations

    def request_token(self, revoke=False):
        """Request and return a new token for the user"""

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
        base_error_message = (
            "Failed to connect to Nuxeo Content Automation server %r"
            " with user %r"
        ) % (self.server_url, self.user_id)
        cookies = list(self.cookie_jar) if self.cookie_jar is not None else []
        try:
            log.trace("Calling '%s' with headers: %r and cookies %r",
                url, headers, cookies)
            req = urllib2.Request(url, headers=headers)
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
        cookies = list(self.cookie_jar) if self.cookie_jar is not None else []
        log.trace("Got token '%s' with cookies %r", token, cookies)
        # Use the (potentially re-newed) token from now on
        if not revoke:
            self._update_auth(token=token)
        return token

    def revoke_token(self):
        self.request_token(revoke=True)

    def wait(self):
        self.execute("NuxeoDrive.WaitForAsyncCompletion")

    def _update_auth(self, password=None, token=None):
        """Select the most appropriate authentication heads based on credentials"""
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
            'X-Application-Name': self.application_name,
            self.auth[0]: self.auth[1],
        }

    def _check_params(self, command, input, params):
        if command not in self.operations:
            raise ValueError("'%s' is not a registered operations." % command)
        method = self.operations[command]
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
                raise ValueError("Unexpected param '%s' for operation '%s"
                                 % (param, command))
        for param in required_params:
            if not param in params:
                raise ValueError(
                    "Missing required param '%s' for operation '%s'" % (
                        param, command))

        # TODO: add typechecking

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
