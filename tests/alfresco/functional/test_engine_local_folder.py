"""
Functional tests for :meth:`nxdrive.drive.engine.engine.Engine._setup_local_folder`.

Exercises the local sync-root preparation of a real, bound Alfresco engine:
folder creation, the ``check_fs`` opt-out, idempotence on an existing folder,
and the rollback that must not delete a folder the user already had.
"""

from unittest.mock import patch

import pytest

from nxdrive.drive.exceptions import MissingXattrSupport
from nxdrive.drive.options import Options


@pytest.fixture()
def engine(manager_factory):
    """A bound Alfresco engine whose local folder can be manipulated freely."""
    _manager, engine = manager_factory()
    return engine


class TestSetupLocalFolder:
    def test_creates_a_missing_local_folder(self, engine, tmp_path) -> None:
        engine.local_folder = tmp_path / "Alfresco-new"
        assert not engine.local_folder.exists()

        engine._setup_local_folder(True)

        assert engine.local_folder.is_dir()

    def test_existing_folder_is_left_alone(self, engine, tmp_path) -> None:
        engine.local_folder = tmp_path / "Alfresco-existing"
        engine.local_folder.mkdir()
        marker = engine.local_folder / "keep-me.txt"
        marker.write_text("data", encoding="utf-8")

        engine._setup_local_folder(True)

        assert marker.read_text(encoding="utf-8") == "data"

    def test_check_fs_disabled_skips_everything(self, engine, tmp_path) -> None:
        """``--nofscheck`` must not even create the folder."""
        engine.local_folder = tmp_path / "Alfresco-nocheck"

        engine._setup_local_folder(False)

        assert not engine.local_folder.exists()

    def test_sync_feature_disabled_skips_everything(self, engine, tmp_path) -> None:
        engine.local_folder = tmp_path / "Alfresco-nosync"

        with patch("nxdrive.drive.engine.engine.Feature") as feature:
            feature.synchronization = False
            engine._setup_local_folder(True)

        assert not engine.local_folder.exists()

    def test_unusable_filesystem_rolls_back_a_folder_we_created(
        self, engine, tmp_path
    ) -> None:
        """A filesystem without xattr support must not leave a stray folder."""
        engine.local_folder = tmp_path / "Alfresco-rollback"

        with patch.object(
            type(engine), "_check_fs", side_effect=MissingXattrSupport("no xattr")
        ):
            with pytest.raises(MissingXattrSupport):
                engine._setup_local_folder(True)

        assert not engine.local_folder.exists()

    def test_unusable_filesystem_keeps_a_pre_existing_folder(
        self, engine, tmp_path
    ) -> None:
        """Rollback is only for folders we made; the user's data stays put."""
        engine.local_folder = tmp_path / "Alfresco-preexisting"
        engine.local_folder.mkdir()
        marker = engine.local_folder / "user-data.txt"
        marker.write_text("precious", encoding="utf-8")

        with patch.object(
            type(engine), "_check_fs", side_effect=MissingXattrSupport("no xattr")
        ):
            with pytest.raises(MissingXattrSupport):
                engine._setup_local_folder(True)

        assert engine.local_folder.is_dir()
        assert marker.read_text(encoding="utf-8") == "precious"

    def test_real_filesystem_supports_xattr(self, engine, tmp_path) -> None:
        """The sync root lives on a real disk here, so the check must pass."""
        engine.local_folder = tmp_path / "Alfresco-realfs"

        engine._setup_local_folder(not Options.nofscheck)

        assert engine.local_folder.is_dir()
