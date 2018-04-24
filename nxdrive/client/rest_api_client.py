# coding: utf-8
"""Client for the Nuxeo REST API."""

import json
from logging import getLogger

from nuxeo.auth import TokenAuth
from nuxeo.client import Nuxeo
from nuxeo.models import Group

log = getLogger(__name__)


class RestAPIClient(object):
    """Client for the Nuxeo REST API."""

    application_name = 'Nuxeo Drive'

    def __init__(self, server_url, user_id, device_id, client_version,
                 password=None, token=None, timeout=20, cookie_jar=None,
                 proxies=None, proxy_exceptions=None):

        if not server_url.endswith('/'):
            server_url += '/'
        self.server_url = server_url
        self.user_id = user_id
        self.device_id = device_id
        self.client_version = client_version
        self.timeout = timeout

        self.client = Nuxeo(host=server_url, app_name=self.application_name,
                            cookie_jar=cookie_jar, proxies=proxies)
        self._update_auth(password=password, token=token)

        # Build URL opener
        self.cookie_jar = cookie_jar

    def __repr__(self):
        attrs = ', '.join('{}={!r}'.format(attr, getattr(self, attr, None))
                          for attr in sorted(self.__init__.__code__.co_varnames[1:]))
        return '<{} {}>'.format(self.__class__.__name__, attrs)

    def execute(self, relative_url, method='GET', body=None, adapter=None,
                timeout=-1):
        """Execute a REST API call"""
        url = '/'.join([self.client.client.api_path, relative_url])
        if adapter:
            url += '/@' + adapter

        data = json.dumps(body) if body else None
        resp = self.client.client.request(method, url, data=data)

        try:
            return resp.json()
        except ValueError:
            return resp.content

    def _update_auth(self, password=None, token=None):
        """Select the most appropriate auth headers based on credentials"""
        if token:
            self.client.client.auth = TokenAuth(token)
        elif password:
            self.client.client.auth = (self.user_id, password)
        else:
            raise ValueError('Either password or token must be provided')

    def get_group_names(self):
        return [entry['groupname'] for entry in
                self.execute('groups/search?q=*')['entries']]

    def create_group(self, name, member_users=None, member_groups=None):
        group = Group(groupname=name, member_users=member_users,
                      member_groups=member_groups)
        return self.client.groups.create(group)

    def delete_group(self, name):
        self.client.groups.delete(name)

    def update_group(self, name, member_users=None, member_groups=None):
        group = Group(groupname=name, member_users=member_users,
            member_groups=member_groups)
        return self.client.groups.put(group)
