"""Unit tests for :mod:`nxdrive.alfresco.sync_filters`.

Pure-function tests — no network / no Alfresco client dependency.
"""

from unittest.mock import patch

import pytest

from nxdrive.alfresco.sync_filters import (
    HARDCODED_EXCLUDED_TOP_FOLDERS,
    is_top_folder_excluded,
)


class TestHardcodedExclusions:
    """The hard-coded exclusion list is a stable contract."""

    def test_list_is_non_empty_tuple(self) -> None:
        assert isinstance(HARDCODED_EXCLUDED_TOP_FOLDERS, tuple)
        assert HARDCODED_EXCLUDED_TOP_FOLDERS  # non-empty

    def test_all_entries_are_rooted_under_company_home(self) -> None:
        for entry in HARDCODED_EXCLUDED_TOP_FOLDERS:
            assert entry.startswith("/Company Home/")

    def test_known_system_folders_present(self) -> None:
        # Sample a few well-known entries so a rename is caught early.
        assert "/Company Home/Data Dictionary" in HARDCODED_EXCLUDED_TOP_FOLDERS
        assert "/Company Home/Guest Home" in HARDCODED_EXCLUDED_TOP_FOLDERS
        assert "/Company Home/Sites/rm" in HARDCODED_EXCLUDED_TOP_FOLDERS


class TestIsTopFolderExcluded:
    """Runtime rule for a path *P*:

    Skip *P* if:
        (*P* is under HARDCODED_EXCLUDED_TOP_FOLDERS
         **and** *P* is **not** in ``alfresco_force_sync_top_folders``)
        **or** *P* is under ``alfresco_excluded_top_folders``.
    """

    def test_empty_path_is_not_excluded(self) -> None:
        assert is_top_folder_excluded("") is False

    def test_normal_folder_is_not_excluded(self) -> None:
        assert is_top_folder_excluded("/Company Home/Sites/marketing") is False

    def test_hardcoded_folder_is_excluded(self) -> None:
        assert is_top_folder_excluded("/Company Home/Data Dictionary") is True

    def test_descendant_of_hardcoded_folder_is_excluded(self) -> None:
        assert is_top_folder_excluded("/Company Home/Data Dictionary/Models") is True

    def test_rm_site_is_excluded(self) -> None:
        assert is_top_folder_excluded("/Company Home/Sites/rm") is True
        assert is_top_folder_excluded("/Company Home/Sites/rm/documentLibrary") is True

    def test_sites_root_itself_is_not_excluded(self) -> None:
        assert is_top_folder_excluded("/Company Home/Sites") is False

    def test_matching_is_case_insensitive(self) -> None:
        # The docstring explicitly promises casefold matching.
        assert is_top_folder_excluded("/COMPANY HOME/data dictionary/models") is True


class TestForceSyncOverride:
    """``alfresco_force_sync_top_folders`` re-enables hard-coded entries."""

    def test_force_sync_re_enables_hardcoded_folder(self) -> None:
        with patch("nxdrive.alfresco.sync_filters.Options") as opts:
            opts.alfresco_force_sync_top_folders = "/Guest Home"
            opts.alfresco_excluded_top_folders = ""
            assert is_top_folder_excluded("/Company Home/Guest Home") is False

    def test_force_sync_accepts_short_form_path(self) -> None:
        # Admins may or may not prefix with /Company Home.
        with patch("nxdrive.alfresco.sync_filters.Options") as opts:
            opts.alfresco_force_sync_top_folders = "Guest Home"
            opts.alfresco_excluded_top_folders = ""
            assert is_top_folder_excluded("/Company Home/Guest Home") is False


class TestExtraExcludedOverride:
    """``alfresco_excluded_top_folders`` adds new exclusions."""

    def test_admin_can_add_extra_exclusion(self) -> None:
        with patch("nxdrive.alfresco.sync_filters.Options") as opts:
            opts.alfresco_force_sync_top_folders = ""
            opts.alfresco_excluded_top_folders = "/Company Home/Sites/marketing"
            assert is_top_folder_excluded("/Company Home/Sites/marketing") is True

    def test_extra_exclusion_wins_over_force_sync(self) -> None:
        # Precedence rule from the module docstring.
        with patch("nxdrive.alfresco.sync_filters.Options") as opts:
            opts.alfresco_force_sync_top_folders = "/Guest Home"
            opts.alfresco_excluded_top_folders = "/Guest Home"
            assert is_top_folder_excluded("/Company Home/Guest Home") is True


@pytest.mark.parametrize(
    "path,expected",
    [
        ("/Company Home", False),
        ("/Company Home/", False),
        ("/Company Home/User Homes", True),
        ("/Company Home/User Homes/admin", True),
        ("/Company Home/IMAP Home", True),
        ("/Company Home/IMAP Attachments", True),
        ("/Company Home/Shared", False),
    ],
)
def test_various_paths(path: str, expected: bool) -> None:
    """Table-driven sanity coverage."""
    with patch("nxdrive.alfresco.sync_filters.Options") as opts:
        opts.alfresco_force_sync_top_folders = ""
        opts.alfresco_excluded_top_folders = ""
        assert is_top_folder_excluded(path) is expected
