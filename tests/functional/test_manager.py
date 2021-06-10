import os

import pytest

from nxdrive.exceptions import NoAssociatedSoftware

from ..markers import windows_only


@windows_only
def test_open_local_file_no_soft(manager_factory, monkeypatch):
    """
    Ensure that manager.open_local_file() raises our exception
    when there is no associated software.
    """

    def startfile(path):
        raise OSError(
            1155,
            "No application is associated with the specified file for this operation.",
            path,
            1155,
        )

    monkeypatch.setattr(os, "startfile", startfile)
    with manager_factory(with_engine=False) as manager, pytest.raises(
        NoAssociatedSoftware
    ):
        manager.open_local_file("File.azerty")
