from nxdrive import __version__
from nxdrive.options import Options
from nxdrive.updater.base import BaseUpdater

NEXT_VER = ".".join(f"{v + 1}" for v in map(int, __version__.split(".")))
VERSIONS = {
    __version__: {"type": "release", "min": "10.10"},
    NEXT_VER: {
        "type": "release",
        "min": "10.10",
        "checksum": {
            "algo": "sha256",
            "foo": "f09999db127d04cdbf9d401101d0ed81898c781e4408102180df2b83bc1fdda4",
        },
    },
    "4.4.0": {
        "type": "release",
        "min": "10.10",
        "checksum": {
            "algo": "sha256",
            "foo": "f09999db127d04cdbf9d401101d0ed81898c781e4408102180df2b83bc1fdda4",
        },
    },
}


class Updater(BaseUpdater):
    def __init__(self, *args):
        super().__init__(*args)

        self.ext = "foo"
        self.release_file = "nuxeo-drive-{version}.foo"

        self.checkpoint = False

    @property
    def server_ver(self):
        return "10.10"

    def install(self, filename: str) -> None:
        self.checkpoint = True

    def _fetch_versions(self):
        self.versions = VERSIONS


def check_attrs(updater, enable: bool, checkpoint: bool, version: str):
    assert updater.enable is enable
    updater.refresh_status()
    assert updater.checkpoint is checkpoint
    assert updater.version == version


def test_not_frozen(manager_factory):
    """Simple test when the application is not frozen."""
    Options.is_frozen = False

    with manager_factory(with_engine=False) as manager:
        updater = Updater(manager)
        check_attrs(updater, False, False, "")


@Options.mock()
def test_frozen(manager_factory):
    """Simple test when the application is frozen."""
    Options.is_frozen = True

    with manager_factory(with_engine=False) as manager:
        updater = Updater(manager)
        check_attrs(updater, True, True, NEXT_VER)


@Options.mock()
def test_frozen_updates_disabled(manager_factory):
    """Simple test when the application is frozen and auto-update disabled."""
    Options.is_frozen = True
    Options.update_check_delay = 0

    with manager_factory(with_engine=False) as manager:
        updater = Updater(manager)
        check_attrs(updater, False, False, "")


@Options.mock()
def test_frozen_updates_disabled_centralized(manager_factory):
    """Simple test when:
        - the application is frozen
        - auto-update disabled
        - channel set to centralized
    """
    Options.channel = "centralized"
    Options.is_frozen = True
    Options.update_check_delay = 0

    with manager_factory(with_engine=False) as manager:
        updater = Updater(manager)
        check_attrs(updater, False, False, "")


@Options.mock()
def test_frozen_updates_disabled_centralized_client_version(manager_factory):
    """Simple test when:
        - the application is frozen
        - auto-update disabled
        - channel set centralized
        - client_version is set

    This scenario should unlock the auto-update. See NXDRIVE-2047.
    """
    Options.channel = "centralized"
    Options.client_version = "4.4.0"
    Options.is_frozen = True
    Options.update_check_delay = 0

    with manager_factory(with_engine=False) as manager:
        updater = Updater(manager)
        check_attrs(updater, True, True, "4.4.0")
        # The interval is modified, checks its value
        assert updater._check_interval == 3600
