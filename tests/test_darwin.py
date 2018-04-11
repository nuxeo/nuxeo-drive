# coding: utf-8
import pytest

from nxdrive.osi import AbstractOSIntegration


def is_folder_registered(os, name):
    lst = os._get_favorite_list()
    return os._find_item_in_list(lst, name) is not None


@pytest.mark.skipif(not AbstractOSIntegration.is_mac(), reason='macOS only.')
def test_folder_registration():
    name = 'TestCazz'

    # Unregister first; to ensure favorite bar is cleaned.
    os = AbstractOSIntegration.get(None)
    os.unregister_folder_link(name)
    assert not is_folder_registered(os, name)

    os.register_folder_link('.', name)
    assert is_folder_registered(os, name)

    os.unregister_folder_link(name)
    assert not is_folder_registered(os, name)
