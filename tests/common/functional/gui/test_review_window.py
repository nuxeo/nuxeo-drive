#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""End-to-end tests of the Direct Transfer selection review window.

Unlike the unit tests, these drive a *real* ``FoldersDialog`` so that the whole
round trip is covered: open the review window, tick some rows, confirm, and
check that the upload queue and the dialog summary were both updated.
"""

import shutil
from unittest.mock import MagicMock, patch

import pytest

from nxdrive.drive.gui import folders_dialog as folders_dialog_module
from nxdrive.drive.gui.folders_dialog import FoldersDialog
from nxdrive.drive.gui.review_window import ReviewFileModel, ReviewSelectionDialog
from nxdrive.drive.qt import constants as qt
from nxdrive.drive.qt.imports import (
    QCoreApplication,
    QEvent,
    QIcon,
    QModelIndex,
    QTreeView,
    Signal,
)
from nxdrive.drive.translator import Translator
from nxdrive.drive.utils import find_resource, sizeof_fmt


@pytest.fixture(scope="module", autouse=True)
def translator():
    if Translator.singleton is None:
        Translator(find_resource("i18n"), lang="en")


@pytest.fixture
def keep_widget(qapp):
    """Track widgets and dispose of them before the QApplication is torn down.

    Widgets are registered parents first, so deleting in reverse order takes
    the children down before the dialog owning them. Pending deletions are
    flushed right away: a deferred delete running later, while another widget
    is being built, crashes the interpreter.
    """
    widgets = []

    def keep(widget):
        widgets.append(widget)
        return widget

    yield keep

    for widget in reversed(widgets):
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


@pytest.fixture
def engine():
    engine = MagicMock()
    engine.type = "nuxeo"
    engine.remote_user = "alice"
    engine.have_folder_upload = True
    engine.remote.get_doc_enricher.side_effect = lambda _ref, _name, folder=False: (
        ["Folder", "CustomFolder"] if folder else ["File", "CustomFile"]
    )
    engine.dao.get_config.side_effect = lambda key, default=None: default
    return engine


@pytest.fixture
def application():
    application = MagicMock()
    application.icon = QIcon()
    application.is_dark_mode.return_value = False
    return application


class StubFolderTreeView(QTreeView):
    """A real QWidget exposing the small FolderTreeView API the dialog uses."""

    update = Signal()

    def __init__(self):
        super().__init__()
        self.current = QModelIndex()
        self.get_item_from_position = MagicMock(return_value=None)
        self.is_item_enabled = MagicMock(return_value=True)
        self.expand_current_selected = MagicMock()
        self.select_item_from_path = MagicMock()


@pytest.fixture
def tree_view(monkeypatch):
    tree = StubFolderTreeView()
    monkeypatch.setattr(FoldersDialog, "get_tree_view", lambda _self: tree)
    return tree


@pytest.fixture
def local_tree(tmp_path):
    """A real folder holding a sub-folder and two files.

    Zero byte files are skipped by the dialog, so every file has content. The
    root holds more than one entry on purpose: ticking a single one must not
    end up ticking the root as well.
    """
    root = tmp_path / "upload"
    nested = root / "nested"
    nested.mkdir(parents=True)

    report = root / "report.txt"
    report.write_bytes(b"report")
    memo = root / "memo.txt"
    memo.write_bytes(b"memo")
    inner = nested / "inner.txt"
    inner.write_bytes(b"inner-data")

    return {
        "root": root,
        "nested": nested,
        "report": report,
        "memo": memo,
        "inner": inner,
    }


@pytest.fixture
def dialog(keep_widget, application, engine, tree_view, local_tree):
    return keep_widget(
        FoldersDialog(application, engine, local_tree["root"], "/remote")
    )


@pytest.fixture
def open_review(keep_widget):
    """Open a real review window on top of a folders dialog."""

    def _open(folders_dialog, /):
        return keep_widget(ReviewSelectionDialog(folders_dialog))

    return _open


def item_for(model, path, /):
    for item in model.iter_items():
        if item.data(model.PATH_ROLE) == path:
            return item
    raise AssertionError(f"No row found for {path}")


def listed_paths(window, /):
    return {item.data(ReviewFileModel.PATH_ROLE) for item in window.model.iter_items()}


def test_selection_is_populated_from_a_real_folder(dialog, local_tree):
    """The dialog queues the folder, its sub-folder and the files inside."""
    assert set(dialog.paths) == {
        local_tree["root"],
        local_tree["nested"],
        local_tree["report"],
        local_tree["memo"],
        local_tree["inner"],
    }
    # Folders are queued with a size of 0, files with their real size
    assert dialog.paths[local_tree["root"]] == 0
    assert dialog.paths[local_tree["report"]] == 6
    assert dialog.paths[local_tree["inner"]] == 10
    assert dialog.overall_size == 20


def test_review_button_follows_the_selection(
    keep_widget, application, engine, tree_view, local_tree
):
    empty = keep_widget(FoldersDialog(application, engine, None, "/remote"))

    assert not empty.paths
    assert not empty.review_selection_button.isEnabled()

    empty._process_additionnal_local_paths([str(local_tree["report"])])
    assert empty.review_selection_button.isEnabled()


def test_review_button_is_wired_to_the_review_action(dialog):
    with patch.object(FoldersDialog, "_review_selection_action") as action:
        dialog.review_selection_button.click()
    action.assert_called_once_with()


def test_review_action_builds_and_shows_the_review_window(dialog):
    # The class is swapped out rather than its exec(): patching a C++ virtual
    # on a PySide6 type crashes the interpreter.
    with patch.object(folders_dialog_module, "ReviewSelectionDialog") as window_cls:
        dialog._review_selection_action()

    window_cls.assert_called_once_with(dialog)
    window_cls.return_value.exec.assert_called_once_with()


def test_review_window_lists_every_queued_path(dialog, open_review):
    window = open_review(dialog)
    assert listed_paths(window) == set(dialog.paths)


def test_removing_one_file_updates_the_queue_and_the_summary(
    dialog, open_review, local_tree
):
    window = open_review(dialog)
    item_for(window.model, local_tree["report"]).setCheckState(qt.Checked)
    window.accept()

    assert local_tree["report"] not in dialog.paths
    assert local_tree["memo"] in dialog.paths
    assert local_tree["inner"] in dialog.paths
    assert dialog.overall_size == 14
    assert dialog.local_paths_size_lbl.text() == sizeof_fmt(14)
    assert dialog.local_path.text() == dialog._files_display()
    assert dialog.upload_now_button.isEnabled()


def test_removing_a_folder_also_removes_everything_it_holds(
    dialog, open_review, local_tree
):
    window = open_review(dialog)
    item_for(window.model, local_tree["nested"]).setCheckState(qt.Checked)
    window.accept()

    assert local_tree["nested"] not in dialog.paths
    assert local_tree["inner"] not in dialog.paths
    assert set(dialog.paths) == {
        local_tree["root"],
        local_tree["report"],
        local_tree["memo"],
    }
    assert dialog.overall_size == 10


def test_removing_a_folder_deleted_meanwhile_still_clears_its_contents(
    dialog, local_tree
):
    """The queue decides what goes, not the current state of the disk."""
    shutil.rmtree(local_tree["nested"])
    assert not local_tree["nested"].is_dir()

    dialog.remove_local_paths([local_tree["nested"]])

    assert local_tree["nested"] not in dialog.paths
    assert local_tree["inner"] not in dialog.paths
    assert local_tree["report"] in dialog.paths


def test_removing_a_file_never_touches_its_siblings(dialog, local_tree):
    dialog.remove_local_paths([local_tree["report"]])

    assert local_tree["report"] not in dialog.paths
    assert local_tree["memo"] in dialog.paths
    assert local_tree["nested"] in dialog.paths
    assert local_tree["inner"] in dialog.paths


def test_removing_an_unqueued_path_changes_nothing(dialog, tmp_path):
    before = dict(dialog.paths)

    dialog.remove_local_paths([tmp_path / "never-queued.txt"])

    assert dialog.paths == before


def test_ticking_the_last_unticked_file_cascades_up_to_its_folder(
    dialog, open_review, local_tree
):
    """A folder joins the selection once every one of its children is ticked."""
    window = open_review(dialog)
    item_for(window.model, local_tree["inner"]).setCheckState(qt.Checked)
    # nested/ only holds inner.txt, so it follows; the root does not, because
    # report.txt and memo.txt are still unticked
    assert set(window.model.checked_paths()) == {
        local_tree["inner"],
        local_tree["nested"],
    }

    window.accept()
    assert set(dialog.paths) == {
        local_tree["root"],
        local_tree["report"],
        local_tree["memo"],
    }


def test_cancelling_the_review_window_changes_nothing(dialog, open_review):
    before = dict(dialog.paths)
    size_text = dialog.local_paths_size_lbl.text()

    window = open_review(dialog)
    window.model.set_all_checked(True)
    window.reject()

    assert dialog.paths == before
    assert dialog.local_paths_size_lbl.text() == size_text


def test_removing_everything_empties_the_dialog(dialog, open_review):
    window = open_review(dialog)
    window.select_all_button.click()
    assert window.remove_selection_button.isEnabled()
    window.accept()

    assert dialog.paths == {}
    assert dialog.path is None
    assert dialog.local_path.text() == ""
    assert dialog.local_paths_size_lbl.text() == sizeof_fmt(0)
    assert not dialog.upload_now_button.isEnabled()
    assert not dialog.review_selection_button.isEnabled()


def test_removing_the_displayed_path_falls_back_on_a_remaining_one(
    keep_widget, open_review, application, engine, tree_view, local_tree
):
    # Two loose files, so that removing the first one leaves a second behind
    dialog = keep_widget(
        FoldersDialog(application, engine, local_tree["report"], "/remote")
    )
    dialog._process_additionnal_local_paths([str(local_tree["memo"])])
    assert dialog.path == local_tree["report"]

    window = open_review(dialog)
    item_for(window.model, local_tree["report"]).setCheckState(qt.Checked)
    window.accept()

    assert set(dialog.paths) == {local_tree["memo"]}
    assert dialog.path == local_tree["memo"]
    assert dialog.local_path.text() == str(local_tree["memo"])


def test_removing_nothing_leaves_the_dialog_untouched(dialog, open_review):
    before = dict(dialog.paths)
    displayed = dialog.local_path.text()

    window = open_review(dialog)
    # Nothing ticked: the button is disabled and accept() is a no-op
    assert not window.remove_selection_button.isEnabled()
    window.accept()

    assert dialog.paths == before
    assert dialog.local_path.text() == displayed


def test_search_then_remove_only_touches_the_matching_row(
    dialog, open_review, local_tree
):
    window = open_review(dialog)
    window.search.setText("report")
    item_for(window.model, local_tree["report"]).setCheckState(qt.Checked)
    window.accept()

    assert local_tree["report"] not in dialog.paths
    assert local_tree["memo"] in dialog.paths
    assert local_tree["inner"] in dialog.paths
    assert local_tree["nested"] in dialog.paths


def test_two_review_rounds_in_a_row(dialog, open_review, local_tree):
    first = open_review(dialog)
    item_for(first.model, local_tree["report"]).setCheckState(qt.Checked)
    first.accept()

    second = open_review(dialog)
    # The second window is built from the already shrunk selection
    assert local_tree["report"] not in listed_paths(second)
    assert listed_paths(second) == set(dialog.paths)

    item_for(second.model, local_tree["memo"]).setCheckState(qt.Checked)
    second.accept()

    assert set(dialog.paths) == {
        local_tree["root"],
        local_tree["nested"],
        local_tree["inner"],
    }
    assert dialog.overall_size == 10
