#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

from nxdrive.drive.auth import OAuthentication


def test_oauthentication(manager_factory, nuxeo_url):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    oauth = OAuthentication(nuxeo_url, dao=dao, device_id=None)
    assert oauth
