# coding: utf-8
import pytest

from nxdrive.constants import MAC
from nxdrive.osi import AbstractOSIntegration


def is_folder_registered(osi, name):
    lst = osi._get_favorite_list()
    return osi._find_item_in_list(lst, name) is not None


@pytest.mark.skipif(not MAC, reason='macOS only.')
def test_folder_registration():
    name = 'TestCazz'

    # Unregister first; to ensure favorite bar is cleaned.
    osi = AbstractOSIntegration.get(None)
    osi.unregister_folder_link(name)
    assert not is_folder_registered(osi, name)

    osi.register_folder_link('.', name)
    assert is_folder_registered(osi, name)

    osi.unregister_folder_link(name)
    assert not is_folder_registered(osi, name)
