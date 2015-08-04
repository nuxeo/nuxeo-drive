"""Client for the Nuxeo REST API."""

import base64
import json
import urllib2

from nxdrive.logging_config import get_logger

log = get_logger(__name__)


class RestAPIClient(object):
    """Client for the Nuxeo REST API."""

    application_name = 'Nuxeo Drive'

    def __init__(self, server_url, user_id, device_id, client_version,
                 password=None, token=None, timeout=20, cookie_jar=None):

        if not server_url.endswith('/'):
            server_url += '/'
        self.rest_api_url = server_url + 'api/v1/'

        self.user_id = user_id
        self.device_id = device_id
        self.client_version = client_version
        self.timeout = timeout
        self._update_auth(password=password, token=token)

        # Build URL opener
        self.cookie_jar = cookie_jar
        cookie_processor = urllib2.HTTPCookieProcessor(
            cookiejar=cookie_jar)
        self.opener = urllib2.build_opener(cookie_processor)

    def execute(self, relative_url, adapter=None, timeout=-1):
        """Execute a REST API call"""

        url = self.rest_api_url + relative_url
        if adapter is not None:
            url += '/@' + adapter

        headers = {
            "Content-Type": "application/json+nxrequest",
            "Accept": "application/json+nxentity, */*",
        }
        headers.update(self._get_common_headers())

        cookies = self._get_cookies()
        log.trace("Calling REST API %s with headers %r and cookies %r", url,
                  headers, cookies)
        req = urllib2.Request(url, headers=headers)
        timeout = self.timeout if timeout == -1 else timeout
        try:
            resp = self.opener.open(req, timeout=timeout)
        except Exception as e:
            self._log_details(e)
            raise

        return self._read_response(resp, url)

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

    def _read_response(self, response, url):
        info = response.info()
        s = response.read()
        content_type = info.get('content-type', '')
        cookies = self._get_cookies()
        if content_type.startswith("application/json"):
            log.trace("Response for %s with cookies %r: %r",
                url, cookies, s)
            return json.loads(s) if s else None
        else:
            log.trace("Response for %s with cookies %r has content-type %r",
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

    def get_user_full_name(self, userid, adapter=None, timeout=-1):
        """Execute a REST API call to get User Information"""
        return self.execute(relative_url='user/'+ userid)
