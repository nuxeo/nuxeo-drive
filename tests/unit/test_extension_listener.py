from PyQt5.QtNetwork import QAbstractSocket, QHostAddress

from nxdrive.osi.extension import ExtensionListener


def test_host_to_addr():
    # Bad hostname
    assert not ExtensionListener.host_to_addr("")
    assert not ExtensionListener.host_to_addr("blablabla")

    # Good hostname
    address = ExtensionListener.host_to_addr("localhost")
    assert isinstance(address, QHostAddress)
    assert address.protocol() == QAbstractSocket.IPv4Protocol
    assert address.toString() == "127.0.0.1"
