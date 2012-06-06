"""Synchronous calls to the Nuxeo Content Automation HTTP interface."""


class NuxeoClient(object):
    """Basic client for the Nuxeo Content Automation HTTP + JSON API"""

    def __init__(self, server_url, user_id, password):
        self.server_url = server_url
        self.user_id = user_id
        self.password = password

    def authenticate(self):
        # TODO
        return True

    def is_valid_root(self, repo, ref_or_path):
        # TODO
        return True
