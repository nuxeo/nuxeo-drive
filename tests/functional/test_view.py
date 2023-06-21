from nxdrive.gui.view import FileModel


def test_foldersDialog():
    def func():
        return True

    file_model = FileModel(func)
    returned_val = file_model.add_files([{"key": "val"}])
    assert not returned_val
