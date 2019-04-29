import os.path
from pathlib import Path

from nxdrive.engine.activity import Action, FileAction, IdleAction


def test_action():
    action = Action("Testing")
    assert action.type == "Testing"
    assert repr(action)
    assert "%" not in repr(action)

    actions = Action.get_actions()
    assert len(actions) == 1
    assert list(actions.values())[0] == action
    assert Action.get_current_action() == action

    # Will test .get_percent()
    details = action.export()
    assert details["last_transfer"] == "Testing"
    assert details["progress"] == 0.0
    assert isinstance(details["uid"], str)

    Action.finish_action()
    actions = Action.get_actions()
    assert len(actions) == 0
    assert Action.get_current_action() is None


def test_action_with_values():
    action = Action(action_type="Trying", progress=42.222)
    assert "%" in repr(action)
    details = action.export()
    assert details["progress"] == 42.222
    Action.finish_action()


def test_file_action(tmp):
    parent = tmp()
    parent.mkdir()
    filepath = parent / "test.txt"
    size = filepath.write_bytes(b"This is Sparta!")

    action = FileAction("Mocking", filepath)
    assert action.type == "Mocking"

    # Will test .get_percent()
    details = action.export()
    assert details["last_transfer"] == "Mocking"
    assert details["progress"] == 0.0
    assert isinstance(details["uid"], str)
    assert details["size"] == size
    assert details["name"] == filepath.name
    assert details["filepath"] == str(filepath)

    assert Action.get_current_action() == action

    Action.finish_action()
    assert action.finished


def test_file_action_with_values():
    filepath = Path("fake/test.odt")
    action = FileAction("Mocking", filepath, size=42)
    assert action.type == "Mocking"

    # Will test .get_percent()
    details = action.export()
    assert details["size"] == 42
    assert details["name"] == "test.odt"
    assert details["filepath"] == f"fake{os.path.sep}test.odt"


def test_idle_action():
    action = IdleAction()
    assert action.type == "Idle"
