# coding: utf-8
"""Client for the Nuxeo REST API."""

import base64
import json
import urllib2

from nxdrive.client.base_automation_client import get_proxy_handler
from nxdrive.logging_config import get_logger

log = get_logger(__name__)


class RestAPIClient(object):
    """Client for the Nuxeo REST API."""

    application_name = 'Nuxeo Drive'

    def __init__(self, server_url, user_id, device_id, client_version,
                 password=None, token=None, timeout=20, cookie_jar=None,
                 proxies=None, proxy_exceptions=None):

        if not server_url.endswith('/'):
            server_url += '/'
        self.rest_api_url = server_url + 'api/v1/'
        self.server_url = server_url
        self.user_id = user_id
        self.device_id = device_id
        self.client_version = client_version
        self.timeout = timeout
        self._update_auth(password=password, token=token)

        # Build URL opener
        self.cookie_jar = cookie_jar
        cookie_processor = urllib2.HTTPCookieProcessor(
            cookiejar=cookie_jar)
        # Get proxy handler
        proxy_handler = get_proxy_handler(proxies,
                                          proxy_exceptions=proxy_exceptions,
                                          url=self.server_url)
        self.opener = urllib2.build_opener(cookie_processor, proxy_handler)

    def __repr__(self):
        attrs = ', '.join('{}={!r}'.format(attr, getattr(self, attr, None))
                          for attr in sorted(self.__init__.__code__.co_varnames[1:]))
        return '<{} {}>'.format(self.__class__.__name__, attrs)

    def get_acls(self, ref):
        return self.execute('id/' + ref, adapter='acl')

    def execute(self, relative_url, method='GET', body=None, adapter=None, timeout=-1):
        """Execute a REST API call"""

        url = self.rest_api_url + relative_url
        if adapter is not None:
            url += '/@' + adapter

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json+nxentity, */*",
            "X-NXproperties": "*",
            # Keep compatibility with old header name
            "X-NXDocumentProperties": "*",
        }
        headers.update(self._get_common_headers())

        data = json.dumps(body) if body is not None else None

        cookies = self._get_cookies()
        log.trace("Calling REST API %s %s with headers %r, cookies %r and JSON payload %r", method, url, headers,
                  cookies, data)
        req = urllib2.Request(url, data=data, headers=headers)
        req.get_method = lambda: method
        timeout = self.timeout if timeout == -1 else timeout
        try:
            resp = self.opener.open(req, timeout=timeout)
        except Exception as e:
            self._log_details(e)
            raise

        return self._read_response(resp, url, method=method)

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

    def _read_response(self, response, url, method='GET'):
        info = response.info()
        s = response.read()
        content_type = info.get('content-type', '')
        cookies = self._get_cookies()
        if content_type.startswith("application/json"):
            log.trace("Response for %s %s with cookies %r: %r", method, url, cookies, s)
            return json.loads(s) if s else None
        else:
            log.trace("Response for %s %s with cookies %r has content-type %r", method, url, cookies, content_type)
            return s

    def _log_details(self, e):
        if hasattr(e, "fp"):
            detail = e.fp.read()
            try:
                exc = json.loads(detail)
                message = exc.get('message')
                stack = exc.get('stack')
                error = exc.get('error')
                if message:
                    log.debug('Remote exception message: %s', message)
                if stack:
                    log.debug('Remote exception stack: %r', exc['stack'], exc_info=True)
                else:
                    log.debug('Remote exception details: %r', detail)
                return exc.get('status'), exc.get('code'), message, error
            except:
                # Error message should always be a JSON message,
                # but sometimes it's not
                if '<html>' in detail:
                    message = e
                else:
                    message = detail
                log.error(message)
                if isinstance(e, urllib2.HTTPError):
                    return e.code, None, message, None
        return None

    def get_user_full_name(self, userid, adapter=None, timeout=-1):
        """Execute a REST API call to get User Information"""
        return self.execute(relative_url='user/' + userid)

    def get_group_names(self):
        return [entry['groupname'] for entry in self.execute('groups/search?q=*')['entries']]

    def create_group(self, name, member_users=None, member_groups=None):
        group = {
            'entity-type': 'group',
            'groupname': name
        }
        if member_users is not None:
            group['memberUsers'] = member_users
        if member_groups is not None:
            group['memberGroups'] = member_groups
        return self.execute('group', method='POST', body=group)

    def delete_group(self, name):
        self.execute('group/%s' % name, method='DELETE')

    def update_group(self, name, member_users=None, member_groups=None):
        group = {
            'entity-type': 'group',
            'groupname': name
        }
        if member_users is not None:
            group['memberUsers'] = member_users
        if member_groups is not None:
            group['memberGroups'] = member_groups
        return self.execute('group/%s' % name, method='PUT', body=group)
