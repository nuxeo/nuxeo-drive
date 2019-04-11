from nxdrive.notification import Notification


def test_export():
    notif = Notification()
    assert notif.export()
