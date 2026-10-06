"""Deterministic unit tests for the Direct Transfer selection review window."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from nxdrive.drive.gui.review_window import ReviewFileModel, ReviewSelectionDialog
from nxdrive.drive.qt import constants as qt
from nxdrive.drive.qt.imports import QCoreApplication, QDialog, QEvent, Qt
from nxdrive.drive.translator import Translator
from nxdrive.drive.utils import find_resource, sizeof_fmt


@pytest.fixture(scope="module", autouse=True)
def translator():
    if Translator.singleton is None:
        Translator(find_resource("i18n"), lang="en")


@pytest.fixture
def keep_widget(qapp):
    """Track widgets and dispose of them before the QApplication is torn down."""
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
def sample_tree(tmp_path):
    """Create a real on-disk tree: the model calls Path.is_dir() on every path.

    root/
        docs/            -> 3 items below it
            a.txt        (3 bytes)
            notes/       -> 1 item below it
                b.txt    (5 bytes)
        photo.png        (7 bytes)
    """
    docs = tmp_path / "docs"
    notes = docs / "notes"
    notes.mkdir(parents=True)

    a_txt = docs / "a.txt"
    a_txt.write_bytes(b"abc")
    b_txt = notes / "b.txt"
    b_txt.write_bytes(b"defgh")
    photo = tmp_path / "photo.png"
    photo.write_bytes(b"1234567")

    return {
        "root": tmp_path,
        "docs": docs,
        "notes": notes,
        "a_txt": a_txt,
        "b_txt": b_txt,
        "photo": photo,
        "paths": {docs: 8, a_txt: 3, notes: 5, b_txt: 5, photo: 7},
    }


@pytest.fixture
def paths(sample_tree):
    return sample_tree["paths"]


@pytest.fixture
def model(paths):
    return ReviewFileModel(paths)


class FakeFoldersDialog(QDialog):
    """The slice of FoldersDialog the review window actually talks to.

    It must be a real widget because the review window parents itself to it.
    """

    def __init__(self, paths, /):
        super().__init__()
        self.paths = dict(paths)
        self.removed = []

    def remove_local_paths(self, paths, /):
        self.removed.append(list(paths))


@pytest.fixture
def folder_dialog(keep_widget, paths):
    return keep_widget(FakeFoldersDialog(paths))


@pytest.fixture
def dialog(keep_widget, folder_dialog):
    return keep_widget(ReviewSelectionDialog(folder_dialog))


#
# Helpers
#


def item_for(model, path, /):
    """Return the *Name* item standing for *path*."""
    for item in model.iter_items():
        if item.data(model.PATH_ROLE) == path:
            return item
    raise AssertionError(f"No row found for {path}")


def children_of(model, item, /):
    """Return the direct *Name* children of *item*."""
    return [item.child(row, model.NAME) for row in range(item.rowCount())]


def row_is_hidden(dialog, item, /):
    index = item.index()
    return dialog.tree_view.isRowHidden(index.row(), index.parent())


def sibling(model, item, column, /):
    return model.itemFromIndex(item.index().siblingAtColumn(column))


#
# ReviewFileModel: tree construction
#


def test_tree_nests_paths_under_the_folder_holding_them(model, sample_tree):
    roots = children_of(model, model.invisibleRootItem())
    assert {item.data(model.PATH_ROLE) for item in roots} == {
        sample_tree["docs"],
        sample_tree["photo"],
    }

    docs = item_for(model, sample_tree["docs"])
    assert {item.data(model.PATH_ROLE) for item in children_of(model, docs)} == {
        sample_tree["a_txt"],
        sample_tree["notes"],
    }

    notes = item_for(model, sample_tree["notes"])
    assert [item.data(model.PATH_ROLE) for item in children_of(model, notes)] == [
        sample_tree["b_txt"]
    ]

    assert len(list(model.iter_items())) == len(sample_tree["paths"])


def test_folder_names_show_their_recursive_item_count(model, sample_tree):
    assert item_for(model, sample_tree["docs"]).text() == "docs (3)"
    assert item_for(model, sample_tree["notes"]).text() == "notes (1)"


def test_file_names_have_no_item_count(model, sample_tree):
    assert item_for(model, sample_tree["a_txt"]).text() == "a.txt"
    assert item_for(model, sample_tree["photo"]).text() == "photo.png"


def test_item_counts_are_formatted_with_thousands_separators(tmp_path):
    folder = tmp_path / "big"
    folder.mkdir()
    paths = {folder: 0}
    for index in range(1_500):
        child = folder / f"file-{index:04}.txt"
        child.touch()
        paths[child] = 0

    model = ReviewFileModel(paths)
    assert item_for(model, folder).text() == "big (1,500)"


def test_row_holds_type_size_and_path_columns(model, sample_tree):
    docs = item_for(model, sample_tree["docs"])
    assert sibling(model, docs, model.TYPE).text() == Translator.get("FOLDER")
    assert sibling(model, docs, model.SIZE).text() == sizeof_fmt(8)
    assert sibling(model, docs, model.PATH).text() == str(sample_tree["docs"])
    assert sibling(model, docs, model.PATH).toolTip() == str(sample_tree["docs"])

    photo = item_for(model, sample_tree["photo"])
    assert sibling(model, photo, model.TYPE).text() == Translator.get("FILE")
    assert sibling(model, photo, model.SIZE).text() == sizeof_fmt(7)


def test_headers_are_translated(model):
    headers = [
        model.horizontalHeaderItem(column).text()
        for column in (model.NAME, model.TYPE, model.SIZE, model.PATH)
    ]
    assert headers == [
        Translator.get("NAME"),
        Translator.get("TYPE"),
        Translator.get("SIZE"),
        Translator.get("PATH"),
    ]


def test_sort_data_keeps_sizes_numeric_and_names_bare(model, sample_tree):
    """Sorting uses UserRole so "9 B" sorts before "10 KiB", not after."""
    assert model.sortRole() == qt.UserRole

    docs = item_for(model, sample_tree["docs"])
    # The bare name, without the "(3)" suffix, so the count cannot skew sorting
    assert docs.data(qt.UserRole) == "docs"
    assert sibling(model, docs, model.SIZE).data(qt.UserRole) == 8
    assert (
        sibling(model, docs, model.PATH).data(qt.UserRole)
        == str(sample_tree["docs"]).lower()
    )


def test_every_row_starts_unchecked_checkable_and_read_only(model):
    for item in model.iter_items():
        assert item.isCheckable()
        assert not item.isEditable()
        assert item.checkState() == qt.Unchecked
        assert item.data(model.STATE_ROLE) == qt.Unchecked


def test_empty_selection_builds_an_empty_tree():
    model = ReviewFileModel({})
    assert list(model.iter_items()) == []
    assert model.checked_paths() == []
    assert not model.has_checked()
    # Nothing to select means "all selected" must stay False
    assert not model.is_all_checked()


def test_a_self_parenting_root_path_is_kept_as_a_root_row(tmp_path):
    """A filesystem root is its own parent, and must still get its own row."""
    root = Path(tmp_path.anchor)

    model = ReviewFileModel({root: 0})

    (item,) = list(model.iter_items())
    assert item.data(model.PATH_ROLE) == root
    assert str(root) in item.text()


def test_contents_of_a_self_parenting_root_still_nest_under_it(tmp_path):
    root = Path(tmp_path.anchor)
    child = root / tmp_path.relative_to(root).parts[0]

    model = ReviewFileModel({root: 0, child: 0})

    root_item = item_for(model, root)
    assert [item.data(model.PATH_ROLE) for item in children_of(model, root_item)] == [
        child
    ]


#
# ReviewFileModel: check state propagation
#


def test_checking_a_folder_checks_everything_it_holds(model, sample_tree):
    item_for(model, sample_tree["docs"]).setCheckState(qt.Checked)

    assert set(model.checked_paths()) == {
        sample_tree["docs"],
        sample_tree["a_txt"],
        sample_tree["notes"],
        sample_tree["b_txt"],
    }
    # A sibling outside that folder is untouched
    assert item_for(model, sample_tree["photo"]).checkState() == qt.Unchecked


def test_unchecking_a_folder_unchecks_everything_it_holds(model, sample_tree):
    docs = item_for(model, sample_tree["docs"])
    docs.setCheckState(qt.Checked)
    docs.setCheckState(qt.Unchecked)

    assert model.checked_paths() == []


def test_unchecking_one_file_unchecks_its_parents_but_not_its_siblings(
    model, sample_tree
):
    item_for(model, sample_tree["docs"]).setCheckState(qt.Checked)
    item_for(model, sample_tree["b_txt"]).setCheckState(qt.Unchecked)

    assert item_for(model, sample_tree["b_txt"]).checkState() == qt.Unchecked
    # Both folders above it lose their tick
    assert item_for(model, sample_tree["notes"]).checkState() == qt.Unchecked
    assert item_for(model, sample_tree["docs"]).checkState() == qt.Unchecked
    # The sibling file keeps its own state
    assert item_for(model, sample_tree["a_txt"]).checkState() == qt.Checked


def test_a_folder_is_checked_only_once_all_of_its_contents_are(model, sample_tree):
    item_for(model, sample_tree["a_txt"]).setCheckState(qt.Checked)
    assert item_for(model, sample_tree["docs"]).checkState() == qt.Unchecked

    # notes/ is still unchecked, so docs/ must stay unchecked too
    item_for(model, sample_tree["b_txt"]).setCheckState(qt.Checked)
    assert item_for(model, sample_tree["notes"]).checkState() == qt.Checked
    assert item_for(model, sample_tree["docs"]).checkState() == qt.Checked


def test_checking_a_root_file_does_not_touch_anything_else(model, sample_tree):
    item_for(model, sample_tree["photo"]).setCheckState(qt.Checked)
    assert model.checked_paths() == [sample_tree["photo"]]


def test_set_all_checked_both_ways(model, sample_tree):
    model.set_all_checked(True)
    assert model.is_all_checked()
    assert model.has_checked()
    assert set(model.checked_paths()) == set(sample_tree["paths"])

    model.set_all_checked(False)
    assert not model.is_all_checked()
    assert not model.has_checked()
    assert model.checked_paths() == []


def test_has_checked_and_is_all_checked_track_partial_selections(model, sample_tree):
    assert not model.has_checked()
    assert not model.is_all_checked()

    item_for(model, sample_tree["photo"]).setCheckState(qt.Checked)
    assert model.has_checked()
    assert not model.is_all_checked()


def test_selection_changed_fires_once_per_user_action(model, sample_tree):
    listener = Mock()
    model.selectionChanged.connect(listener)

    # One click on a folder ticks 4 rows but must emit a single signal
    item_for(model, sample_tree["docs"]).setCheckState(qt.Checked)
    assert listener.call_count == 1

    model.set_all_checked(False)
    assert listener.call_count == 2


def test_setting_the_same_state_again_emits_nothing(model, sample_tree):
    listener = Mock()
    model.selectionChanged.connect(listener)

    item_for(model, sample_tree["photo"]).setCheckState(qt.Unchecked)
    listener.assert_not_called()


def test_changing_a_non_name_column_is_not_a_selection_change(model, sample_tree):
    listener = Mock()
    model.selectionChanged.connect(listener)

    sibling(model, item_for(model, sample_tree["photo"]), model.SIZE).setText("ignored")
    listener.assert_not_called()


def test_checked_paths_returns_real_path_objects(model, sample_tree):
    item_for(model, sample_tree["photo"]).setCheckState(qt.Checked)
    (path,) = model.checked_paths()
    assert isinstance(path, Path)
    assert path == sample_tree["photo"]


#
# ReviewSelectionDialog: construction
#


def test_dialog_builds_the_expected_controls(dialog, paths):
    assert dialog.windowTitle() == Translator.get("REVIEW_SELECTION")
    assert dialog.search.placeholderText() == Translator.get("REVIEW_SEARCH")
    assert dialog.search.isClearButtonEnabled()
    assert dialog.cancel_button.text() == Translator.get("CANCEL")
    assert dialog.remove_selection_button.text() == Translator.get("REMOVE_SELECTION")
    assert len(list(dialog.model.iter_items())) == len(paths)


def test_tree_view_starts_collapsed_and_sortable(dialog, sample_tree):
    assert dialog.tree_view.rootIsDecorated()
    assert dialog.tree_view.itemsExpandable()
    # Folders only open via their arrow, never on a double click on the row
    assert not dialog.tree_view.expandsOnDoubleClick()
    assert dialog.tree_view.isSortingEnabled()

    for folder in ("docs", "notes"):
        item = item_for(dialog.model, sample_tree[folder])
        assert not dialog.tree_view.isExpanded(item.index())


def test_remove_button_is_disabled_until_something_is_checked(dialog, sample_tree):
    assert not dialog.remove_selection_button.isEnabled()

    item_for(dialog.model, sample_tree["photo"]).setCheckState(qt.Checked)
    assert dialog.remove_selection_button.isEnabled()

    item_for(dialog.model, sample_tree["photo"]).setCheckState(qt.Unchecked)
    assert not dialog.remove_selection_button.isEnabled()


def test_select_all_button_toggles_its_label_and_the_whole_tree(dialog):
    assert dialog.select_all_button.text() == Translator.get("REVIEW_SELECT_ALL")

    dialog.select_all_button.click()
    assert dialog.model.is_all_checked()
    assert dialog.select_all_button.text() == Translator.get("REVIEW_DESELECT_ALL")

    dialog.select_all_button.click()
    assert not dialog.model.has_checked()
    assert dialog.select_all_button.text() == Translator.get("REVIEW_SELECT_ALL")


def test_unchecking_one_row_turns_deselect_all_back_into_select_all(
    dialog, sample_tree
):
    dialog.select_all_button.click()
    assert dialog.select_all_button.text() == Translator.get("REVIEW_DESELECT_ALL")

    item_for(dialog.model, sample_tree["photo"]).setCheckState(qt.Unchecked)
    assert dialog.select_all_button.text() == Translator.get("REVIEW_SELECT_ALL")


def test_buttons_state_on_an_empty_selection(keep_widget):
    folder_dialog = keep_widget(FakeFoldersDialog({}))
    dialog = keep_widget(ReviewSelectionDialog(folder_dialog))

    assert not dialog.remove_selection_button.isEnabled()
    assert dialog.select_all_button.text() == Translator.get("REVIEW_SELECT_ALL")


#
# ReviewSelectionDialog: search
#


def test_search_hides_the_rows_that_do_not_match(dialog, sample_tree):
    dialog.search.setText("photo")

    assert not row_is_hidden(dialog, item_for(dialog.model, sample_tree["photo"]))
    assert row_is_hidden(dialog, item_for(dialog.model, sample_tree["docs"]))


def test_search_keeps_and_expands_the_folders_holding_a_match(dialog, sample_tree):
    dialog.search.setText("b.txt")

    model = dialog.model
    docs = item_for(model, sample_tree["docs"])
    notes = item_for(model, sample_tree["notes"])

    assert not row_is_hidden(dialog, item_for(model, sample_tree["b_txt"]))
    assert not row_is_hidden(dialog, notes)
    assert not row_is_hidden(dialog, docs)
    # Expanded so the match can actually be seen
    assert dialog.tree_view.isExpanded(docs.index())
    assert dialog.tree_view.isExpanded(notes.index())
    # The non-matching branches are gone
    assert row_is_hidden(dialog, item_for(model, sample_tree["a_txt"]))
    assert row_is_hidden(dialog, item_for(model, sample_tree["photo"]))


def test_matching_a_folder_keeps_all_of_its_contents_visible(dialog, sample_tree):
    dialog.search.setText("docs")

    model = dialog.model
    for key in ("docs", "a_txt", "notes", "b_txt"):
        assert not row_is_hidden(dialog, item_for(model, sample_tree[key]))
    assert row_is_hidden(dialog, item_for(model, sample_tree["photo"]))


def test_search_is_case_insensitive_and_ignores_surrounding_spaces(dialog, sample_tree):
    dialog.search.setText("   PHOTO   ")
    assert not row_is_hidden(dialog, item_for(dialog.model, sample_tree["photo"]))
    assert row_is_hidden(dialog, item_for(dialog.model, sample_tree["docs"]))


def test_search_ignores_the_item_count_shown_next_to_a_folder_name(dialog, sample_tree):
    """ "docs (3)" must not be found by searching "3"."""
    dialog.search.setText("3")
    assert row_is_hidden(dialog, item_for(dialog.model, sample_tree["docs"]))


def test_search_without_a_match_hides_everything(dialog, sample_tree):
    dialog.search.setText("no-such-thing")
    for item in dialog.model.iter_items():
        assert row_is_hidden(dialog, item)


def test_clearing_the_search_restores_and_collapses_everything(dialog, sample_tree):
    dialog.search.setText("b.txt")
    dialog.search.setText("")

    model = dialog.model
    for item in model.iter_items():
        assert not row_is_hidden(dialog, item)
    for folder in ("docs", "notes"):
        assert not dialog.tree_view.isExpanded(
            item_for(model, sample_tree[folder]).index()
        )


def test_search_does_not_change_the_check_states(dialog, sample_tree):
    item_for(dialog.model, sample_tree["photo"]).setCheckState(qt.Checked)

    dialog.search.setText("docs")
    dialog.search.setText("")

    assert dialog.model.checked_paths() == [sample_tree["photo"]]


#
# ReviewSelectionDialog: accept / reject
#


def test_accept_hands_the_checked_paths_to_the_folders_dialog(
    dialog, folder_dialog, sample_tree
):
    item_for(dialog.model, sample_tree["photo"]).setCheckState(qt.Checked)
    dialog.accept()

    assert folder_dialog.removed == [[sample_tree["photo"]]]
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_accept_on_a_checked_folder_sends_the_folder_and_its_contents(
    dialog, folder_dialog, sample_tree
):
    item_for(dialog.model, sample_tree["docs"]).setCheckState(qt.Checked)
    dialog.accept()

    (removed,) = folder_dialog.removed
    assert set(removed) == {
        sample_tree["docs"],
        sample_tree["a_txt"],
        sample_tree["notes"],
        sample_tree["b_txt"],
    }


def test_cancel_removes_nothing(dialog, folder_dialog, sample_tree):
    item_for(dialog.model, sample_tree["photo"]).setCheckState(qt.Checked)
    dialog.cancel_button.click()

    assert folder_dialog.removed == []
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_sorting_by_size_orders_on_the_byte_value(dialog, sample_tree):
    dialog.tree_view.sortByColumn(ReviewFileModel.SIZE, Qt.SortOrder.AscendingOrder)

    model = dialog.model
    roots = children_of(model, model.invisibleRootItem())
    sizes = [sibling(model, item, model.SIZE).data(qt.UserRole) for item in roots]
    assert sizes == sorted(sizes)
