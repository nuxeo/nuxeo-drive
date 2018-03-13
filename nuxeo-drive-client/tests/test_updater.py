# coding: utf-8
import pytest

from nxdrive.updater import get_latest_compatible_version


@pytest.fixture(scope='module')
def versions():
    return {
        '1.3.0424': {
            'type': 'release',
            'min': '5.8',
        },
        '2.4.2b1': {
            'type': 'beta',
            'min': '9.1',
        },
        '1.3.0524': {
            'type': 'release',
            'min': '5.9.1',
        },
        '1.4.0622': {
            'type': 'release',
            'min': '5.9.2',
        },
        '2.5.0b1': {
            'type': 'beta',
            'min': '9.2',
        },
    }


def test_get_latest_compatible_version(versions):

    def latest(server_ver, nature='release'):
        return get_latest_compatible_version(versions, nature, server_ver)

    # Unexisting version
    assert latest('0.0.0') == ('', {})

    version, _ = latest('5.8')
    assert version == '1.3.0424'

    version, _ = latest('5.9.1')
    assert version == '1.3.0524'

    version, _ = latest('5.9.2')
    assert version == '1.4.0622'

    version, _ = latest('9.1', nature='beta')
    assert version == '2.4.2b1'

    version, _ = latest('9.2', nature='beta')
    assert version == '2.5.0b1'
