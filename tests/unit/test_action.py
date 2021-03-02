import os.path
from pathlib import Path

from nxdrive.engine.activity import (
    Action,
    DownloadAction,
    FileAction,
    IdleAction,
    LinkingAction,
    UploadAction,
    VerificationAction,
    tooltip,
)


def test_action():
    action = Action("Testing")
    assert action.type == "Testing"
    assert repr(action)
    assert "%" not in repr(action)

    actions = Action.get_actions()
    assert len(actions) == 1
    assert list(actions.values())[0] is action
    assert Action.get_current_action() is action

    # Will test .get_percent()
    details = action.export()
    assert details["action_type"] == "Testing"
    assert details["progress"] == 0.0
    assert isinstance(details["uid"], str)

    # Test progress property setter
    action.progress = 100.0
    details = action.export()
    assert details["progress"] == 100.0

    Action.finish_action()
    actions = Action.get_actions()
    assert len(actions) == 0
    assert Action.get_current_action() is None


def test_action_with_values():
    action = Action("Trying", progress=42.222)
    assert "%" in repr(action)
    details = action.export()
    assert details["progress"] == 42.222
    Action.finish_action()


def test_download_action():
    filepath = Path("fake/test.odt")
    action = DownloadAction(filepath, 0)
    assert action.type == "Download"

    Action.finish_action()
    assert action.finished


def test_file_action(tmp):
    parent = tmp()
    parent.mkdir()
    filepath = parent / "test.txt"
    size = filepath.write_bytes(b"This is Sparta!")

    action = FileAction("Mocking", filepath, size)
    assert action.type == "Mocking"
    assert not action.empty

    # Will test .get_percent()
    details = action.export()
    assert details["action_type"] == "Mocking"
    assert details["progress"] == 0.0
    assert isinstance(details["uid"], str)
    assert details["size"] == size
    assert details["name"] == filepath.name
    assert details["filepath"] == str(filepath)

    assert Action.get_current_action() is action

    # Test repr() when .get_percent() > 0
    action.size = 42
    action.progress = 4.2
    assert repr(action) == "Mocking('test.txt'[42]-10.0)"

    Action.finish_action()
    assert action.finished


def test_file_action_empty_file(tmp):
    parent = tmp()
    parent.mkdir()
    filepath = parent / "test.txt"
    filepath.touch()

    action = FileAction("Mocking", filepath, filepath.stat().st_size)

    assert action.empty
    assert not action.uploaded
    details = action.export()
    assert details["action_type"] == "Mocking"
    assert details["progress"] == 0.0
    assert isinstance(details["uid"], str)
    assert details["size"] == 0
    assert details["name"] == filepath.name
    assert details["filepath"] == str(filepath)

    # Trigger a progression update telling that the file has been uploaded
    action.progress += 0
    assert action.export()["progress"] == 100.0
    assert action.uploaded

    Action.finish_action()


def test_file_action_inexistant_file(tmp):
    parent = tmp()
    parent.mkdir()
    filepath = parent / "test.txt"

    action = FileAction("Mocking", filepath, 0)
    assert action.empty
    assert not action.uploaded

    details = action.export()
    assert details["action_type"] == "Mocking"
    assert details["progress"] == 0.0
    assert isinstance(details["uid"], str)
    assert details["size"] == 0
    assert details["name"] == filepath.name
    assert details["filepath"] == str(filepath)

    Action.finish_action()


def test_file_action_with_values():
    filepath = Path("fake/test.odt")
    action = FileAction("Mocking", filepath, 42)
    assert action.type == "Mocking"

    # Test repr() when .get_percent() equals 0
    assert repr(action) == "Mocking('test.odt'[42])"

    # Will test .get_percent()
    details = action.export()
    assert details["size"] == 42
    assert details["name"] == "test.odt"
    assert details["filepath"] == f"fake{os.path.sep}test.odt"

    # Test progress property setter when .progress < .size
    action.progress = 24.5
    details = action.export()
    assert details["progress"] == 24.5 * 100 / 42.0

    # Test progress property setter when .progress >= .size
    action.progress = 222.0
    details = action.export()
    assert details["progress"] == 100.0
    assert details["uploaded"]

    Action.finish_action()


def test_file_action_signals():
    """Try to mimic QThread signals to test ._connect_reporter()."""

    class Reporter:
        def action_started(self):
            pass

        def action_progressing(self):
            pass

        def action_done(self):
            pass

    filepath = Path("fake/test.odt")
    action = FileAction("Mocking", filepath, 42, reporter=Reporter())

    Action.finish_action()
    assert action.finished


def test_idle_action():
    action = IdleAction()
    assert repr(action) == "Idle"
    assert action.type == "Idle"

    Action.finish_action()
    assert action.finished


def test_tooltip():
    @tooltip("Testing tooltip!")
    def function(a, b=1):
        # There should be 1 action, automatically created by the decorator
        action = Action.get_current_action()
        assert action
        assert action.type == "Testing tooltip!"

        return a * b

    # There is no Action right now
    assert Action.get_current_action() is None

    function(4.2, b=10)

    # There should be no action now that the function has been called
    assert Action.get_current_action() is None


def test_upload_action(tmp):
    folder = tmp()
    folder.mkdir()
    filepath = folder / "test-upload.txt"
    filepath.write_bytes(b"This is Sparta!")

    action = UploadAction(filepath, filepath.stat().st_size)
    assert action.type == "Upload"

    Action.finish_action()
    assert action.finished


def test_verification_action(tmp):
    folder = tmp()
    folder.mkdir()
    filepath = folder / "test.txt"
    filepath.write_bytes(b"This is Sparta!")

    action = VerificationAction(filepath, filepath.stat().st_size)
    assert action.type == "Verification"

    Action.finish_action()
    assert action.finished


def test_finalization_action(tmp):
    folder = tmp()
    folder.mkdir()
    filepath = folder / "test.txt"
    filepath.write_bytes(b"This is Sparta!")

    action = LinkingAction(filepath, filepath.stat().st_size)
    assert action.type == "Linking"

    Action.finish_action()
    assert action.finished
