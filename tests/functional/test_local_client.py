import pathlib
import shutil
from uuid import uuid4

import pytest

from nxdrive.constants import ROOT, WINDOWS

from .. import env


@pytest.mark.skipif(not WINDOWS, reason="Windows only")
def test_rename_with_different_partitions(manager_factory):
    """Ensure we can rename a file between different partitions."""
    second_partoche = pathlib.Path(env.SECOND_PARTITION)
    if not second_partoche.is_dir():
        pytest.skip(f"There is no such {second_partoche!r} partition.")

    local_folder = second_partoche / str(uuid4())
    manager, engine = manager_factory(local_folder=local_folder)
    local = engine.local

    try:
        with manager:
            # Ensure folders are on different partitions
            assert manager.home.drive != local.base_folder.drive

            # Relax permissions for the rest of the test
            local.unset_readonly(engine.local_folder)

            # Create a file
            (engine.local_folder / "file Lower.txt").write_text("azerty")

            # Change the case
            local.rename(pathlib.Path("file Lower.txt"), "File LOWER.txt")

            # The file should have its case modified
            children = local.get_children_info(ROOT)
            assert len(children) == 1
            assert children[0].name == "File LOWER.txt"
    finally:
        local.unset_readonly(engine.local_folder)
        shutil.rmtree(local_folder)
