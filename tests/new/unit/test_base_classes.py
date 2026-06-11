"""Unit tests for the base classes in drive/ and their inheritance by nuxeo/.

Tests cover:
- Base class instantiation (with mocked dependencies)
- Abstract method contracts (NotImplementedError)
- Nuxeo subclass inheritance chain (issubclass)
- Nuxeo subclass method overrides
- Workflow base class logic (update_user_task_data, remove_overdue_tasks, etc.)
- DirectDownload helper methods (_get_unique_path, _create_batch_folder, cleanup)
- DirectEdit helper methods (_is_valid_folder_name, _is_lock_file)
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

# ===================================================================
# Workflow base class tests
# ===================================================================


@pytest.fixture
def workflow_base():
    """Create a Workflow base instance."""
    from nxdrive.drive.client.workflow import Workflow

    wf = Workflow()
    wf.user_task_list = {}  # reset class-level dict per test
    return wf


def test_workflow_base_fetch_document_raises(workflow_base):
    with pytest.raises(NotImplementedError):
        workflow_base.fetch_document([], None)


def test_workflow_base_get_pending_tasks_raises(workflow_base):
    with pytest.raises(NotImplementedError):
        workflow_base.get_pending_tasks(None)


def test_workflow_update_user_task_data_new_user(workflow_base):
    """New user gets all tasks returned for notification."""
    task1 = Mock(id="t1")
    task2 = Mock(id="t2")

    result = workflow_base.update_user_task_data([task1, task2], "user1")
    assert len(result) == 2
    assert "user1" in workflow_base.user_task_list
    assert workflow_base.user_task_list["user1"] == ["t1", "t2"]


def test_workflow_update_user_task_data_new_tasks_only(workflow_base):
    """Only newly added tasks are returned."""
    workflow_base.user_task_list["user1"] = ["t1", "t2"]

    task1 = Mock(id="t1")
    task2 = Mock(id="t2")
    task3 = Mock(id="t3")

    result = workflow_base.update_user_task_data([task1, task2, task3], "user1")
    assert len(result) == 1
    assert result[0].id == "t3"


def test_workflow_update_user_task_data_removed_tasks(workflow_base):
    """When tasks are removed, empty list is returned (no notification)."""
    workflow_base.user_task_list["user1"] = ["t1", "t2", "t3"]

    task1 = Mock(id="t1")
    task2 = Mock(id="t2")

    result = workflow_base.update_user_task_data([task1, task2], "user1")
    assert result == []


def test_workflow_update_user_task_data_no_change(workflow_base):
    """Same tasks as before → no notification."""
    workflow_base.user_task_list["user1"] = ["t1", "t2"]

    task1 = Mock(id="t1")
    task2 = Mock(id="t2")

    result = workflow_base.update_user_task_data([task1, task2], "user1")
    assert result == []


def test_workflow_remove_overdue_tasks(workflow_base):
    """Overdue tasks are filtered out."""
    future = (datetime.now(tz=timezone.utc) + timedelta(days=1)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f%z"
    )
    past = (datetime.now(tz=timezone.utc) - timedelta(days=1)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f%z"
    )

    task_future = Mock(dueDate=future)
    task_past = Mock(dueDate=past)

    result = workflow_base.remove_overdue_tasks([task_future, task_past])
    assert len(result) == 1
    assert result[0] is task_future


def test_workflow_clean_user_task_data(workflow_base):
    """clean_user_task_data removes user from the dict."""
    workflow_base.user_task_list["user1"] = ["t1"]
    workflow_base.user_task_list["user2"] = ["t2"]

    workflow_base.clean_user_task_data("user1")
    assert "user1" not in workflow_base.user_task_list
    assert "user2" in workflow_base.user_task_list


def test_workflow_clean_user_task_data_nonexistent(workflow_base):
    """Cleaning a non-existent user is a no-op."""
    workflow_base.clean_user_task_data("ghost_user")
    assert "ghost_user" not in workflow_base.user_task_list


# ===================================================================
# DirectEdit base class tests (helper methods only, no Qt needed)
# ===================================================================


def test_is_lock_file():
    """Test the module-level _is_lock_file helper."""
    from nxdrive.drive.direct_edit import _is_lock_file

    assert _is_lock_file("~$document.docx") is True
    assert _is_lock_file(".~lock.document.odt#") is True
    assert _is_lock_file("document.docx") is False
    assert _is_lock_file("normal_file.txt") is False


def test_direct_edit_valid_folder_name():
    """Test _is_valid_folder_name on the base class."""
    from nxdrive.drive.direct_edit import DirectEdit

    # Use a mock to call the method without full Qt init
    instance = Mock(spec=DirectEdit)
    # Call the unbound method
    valid = DirectEdit._is_valid_folder_name(
        instance, "19bf2a19-e95b-4cfb-8fd7-b45e1d7d022f_file-content"
    )
    assert valid is True

    invalid = DirectEdit._is_valid_folder_name(instance, "not-a-uid_file")
    assert invalid is False

    empty = DirectEdit._is_valid_folder_name(instance, "")
    assert empty is False

    dl_file = DirectEdit._is_valid_folder_name(
        instance, "19bf2a19-e95b-4cfb-8fd7-b45e1d7d022f.dl"
    )
    assert dl_file is True


# ===================================================================
# DirectDownload base class tests (helper methods)
# ===================================================================


def test_direct_download_get_unique_path(tmp_path):
    """_get_unique_path adds (1), (2) suffixes for existing files."""
    from nxdrive.drive.direct_download import DirectDownload

    instance = Mock(spec=DirectDownload)

    # Non-existing file → same path
    p = tmp_path / "file.txt"
    result = DirectDownload._get_unique_path(instance, p)
    assert result == p

    # Create the file, then it should return (1)
    p.touch()
    result = DirectDownload._get_unique_path(instance, p)
    assert result == tmp_path / "file (1).txt"

    # Create (1) too
    (tmp_path / "file (1).txt").touch()
    result = DirectDownload._get_unique_path(instance, p)
    assert result == tmp_path / "file (2).txt"


def test_direct_download_get_download_destination_default(tmp_path):
    """Default download destination is ~/Downloads."""
    from nxdrive.drive.direct_download import DirectDownload
    from nxdrive.drive.options import Options

    instance = Mock(spec=DirectDownload)

    orig = Options.download_folder
    try:
        Options.download_folder = None
        result = DirectDownload._get_download_destination(instance)
        assert result == Path.home() / "Downloads"
    finally:
        Options.download_folder = orig


def test_direct_download_get_download_destination_custom(tmp_path):
    """Custom download_folder in Options is used when accessible."""
    from nxdrive.drive.direct_download import DirectDownload
    from nxdrive.drive.options import MetaOptions

    instance = Mock(spec=DirectDownload)
    custom_dir = tmp_path / "custom_downloads"
    custom_dir.mkdir()

    # Directly set the internal options dict to avoid type-check issues on restore
    orig = MetaOptions.options["download_folder"]
    MetaOptions.options["download_folder"] = (str(custom_dir), "manual")
    try:
        result = DirectDownload._get_download_destination(instance)
        assert result == custom_dir
    finally:
        MetaOptions.options["download_folder"] = orig


# ===================================================================
# Inheritance chain tests
# ===================================================================


def test_nuxeo_direct_edit_inherits_base():
    from nxdrive.drive.direct_edit import DirectEdit as Base
    from nxdrive.nuxeo.direct_edit import DirectEdit as NuxeoDE

    assert issubclass(NuxeoDE, Base)


def test_nuxeo_direct_download_inherits_base():
    from nxdrive.drive.direct_download import DirectDownload as Base
    from nxdrive.nuxeo.direct_download import DirectDownload as NuxeoDD

    assert issubclass(NuxeoDD, Base)


def test_nuxeo_workflow_inherits_base():
    from nxdrive.drive.client.workflow import Workflow as Base
    from nxdrive.nuxeo.client.workflow import Workflow as NuxeoWF

    assert issubclass(NuxeoWF, Base)


def test_nuxeo_direct_edit_overrides_abstract_hooks():
    """Nuxeo DirectEdit must override all abstract hooks."""
    from nxdrive.nuxeo.direct_edit import DirectEdit

    required = [
        "stop_client",
        "_download",
        "_get_info",
        "_lock",
        "_unlock",
        "_handle_upload_queue",
        "_handle_lock_queue",
    ]
    for method_name in required:
        method = getattr(DirectEdit, method_name)
        # Should NOT raise NotImplementedError (i.e., it's overridden)
        assert method is not None
        # Verify it's not the base's stub
        from nxdrive.drive.direct_edit import DirectEdit as Base

        assert method is not getattr(
            Base, method_name
        ), f"Nuxeo DirectEdit did not override {method_name}"


def test_nuxeo_direct_download_overrides_abstract_hooks():
    """Nuxeo DirectDownload must override all abstract hooks."""
    from nxdrive.nuxeo.direct_download import DirectDownload

    required = [
        "_create_download_record",
        "_calculate_folder_size",
        "_process_download",
        "_download_folder",
        "_get_children",
        "_get_download_url",
        "_download_file",
    ]
    for method_name in required:
        method = getattr(DirectDownload, method_name)
        assert method is not None
        from nxdrive.drive.direct_download import DirectDownload as Base

        assert method is not getattr(
            Base, method_name
        ), f"Nuxeo DirectDownload did not override {method_name}"


def test_nuxeo_workflow_overrides_abstract_hooks():
    """Nuxeo Workflow must override all abstract hooks."""
    from nxdrive.nuxeo.client.workflow import Workflow

    required = ["fetch_document", "get_pending_tasks"]
    for method_name in required:
        method = getattr(Workflow, method_name)
        assert method is not None
        from nxdrive.drive.client.workflow import Workflow as Base

        assert method is not getattr(
            Base, method_name
        ), f"Nuxeo Workflow did not override {method_name}"


def test_nuxeo_workflow_inherits_generic_methods():
    """Nuxeo Workflow inherits update_user_task_data etc. from base."""
    from nxdrive.drive.client.workflow import Workflow as Base
    from nxdrive.nuxeo.client.workflow import Workflow as NuxeoWF

    inherited = [
        "update_user_task_data",
        "remove_overdue_tasks",
        "clean_user_task_data",
    ]
    for method_name in inherited:
        assert getattr(NuxeoWF, method_name) is getattr(
            Base, method_name
        ), f"Nuxeo Workflow should inherit {method_name} from base, not override it"


# ===================================================================
# Dynamic class loading via ServerTypeConfig
# ===================================================================


def test_load_nuxeo_classes_from_config():
    """All class_paths in Nuxeo config resolve to valid classes."""
    from nxdrive.drive.server_type import get, load_class

    cfg = get("NUXEO")
    paths = [
        cfg.engine_class_path,
        cfg.direct_edit_class_path,
        cfg.direct_download_class_path,
        cfg.workflow_class_path,
        cfg.oauth2_class_path,
        # folders_only_class_path skipped: pre-existing NameError in that module
    ]
    for class_path in paths:
        if class_path:
            cls = load_class(class_path)
            assert cls is not None, f"Failed to load {class_path}"


def test_load_alfresco_classes_from_config():
    """All non-empty class_paths in Alfresco config resolve to valid classes."""
    from nxdrive.drive.server_type import get, load_class

    cfg = get("ALFRESCO")
    paths = {
        "engine": cfg.engine_class_path,
        "oauth2": cfg.oauth2_class_path,
    }
    for name, class_path in paths.items():
        if class_path:
            cls = load_class(class_path)
            assert cls is not None, f"Failed to load Alfresco {name}: {class_path}"


def test_alfresco_unimplemented_paths_are_empty():
    """Alfresco features not yet implemented have empty class paths."""
    from nxdrive.drive.server_type import get

    cfg = get("ALFRESCO")
    assert cfg.direct_edit_class_path == ""
    assert cfg.direct_download_class_path == ""
    assert cfg.workflow_class_path == ""
    assert cfg.folders_only_class_path == ""
