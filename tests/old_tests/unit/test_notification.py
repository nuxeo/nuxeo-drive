from nxdrive.drive.notification import Notification


def test_export():
    notif = Notification()
    assert notif.export()
