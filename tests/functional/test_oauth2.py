from nxdrive.auth import OAuthentication


def test_oauthentication(manager_factory, nuxeo_url):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    oauth = OAuthentication(nuxeo_url, dao=dao, device_id=None)
    assert oauth
