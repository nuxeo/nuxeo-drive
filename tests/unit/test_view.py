from unittest.mock import Mock

from nxdrive.gui.view import FileModel
from nxdrive.qt.imports import QModelIndex


def test_foldersDialog():
    def func():
        return True

    file_model = FileModel(func)
    returned_val = file_model.add_files([{"key": "val"}])
    assert not returned_val


def test_set_progress(direct_transfer_model):
    """Test the finalize state after 100% progress"""
    action = {
        "engine": "51a2c2dc641311ee87fb...bfc0ec09fa",
        "doc_pair": 1,
        "progress": "100",
        "action_type": "Linking",
        "finalizing_status": "Finalize the status",
    }

    direct_transfer_model.createIndex = Mock(return_value=1)
    direct_transfer_model.setData = Mock()
    direct_transfer_model.set_progress(direct_transfer_model, action)


def test_data(direct_transfer_model):
    """Test get row data as per role"""
    index = QModelIndex
    index.row = Mock(return_value=0)
    direct_transfer_model.data(
        direct_transfer_model, index, direct_transfer_model.FINALIZING_STATUS
    )
