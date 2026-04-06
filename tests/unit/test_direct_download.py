"""
Unit tests for nxdrive.direct_download module.
"""

import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nxdrive.constants import DirectDownloadStatus
from nxdrive.direct_download import DirectDownload
from nxdrive.engine.engine import ServerBindingSettings
from nxdrive.objects import DirectDownload as DirectDownloadRecord


class MockUrlTestEngine:
    """Mock engine for URL matching tests."""

    def __init__(self, url, user, uid="engine-1"):
        self._url = url
        self._user = user
        self.uid = uid
        self.dao = Mock()
        self.remote = Mock()
        self.server_url = url

    def get_binder(self):
        return ServerBindingSettings(self._url, None, self._user, "/", True)


class TestDirectDownloadInit:
    """Test DirectDownload initialization."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_init_creates_folder(self):
        """Test that __init__ creates the download folder."""
        folder = self.folder / "new_subfolder"
        assert not folder.exists()
        dd = DirectDownload(self.manager, folder)
        assert folder.exists()
        assert dd._manager == self.manager
        assert dd._folder == folder
        assert dd._stop is False
        assert dd._download_folders == []

    def test_init_connects_signals(self):
        """Test that __init__ connects signals."""
        dd = DirectDownload(self.manager, self.folder)
        self.manager.directDownload.connect.assert_called_once_with(dd.download)

    def test_download_folder_property(self):
        """Test download_folder property."""
        dd = DirectDownload(self.manager, self.folder)
        assert dd.download_folder == self.folder

    def test_download_folders_property_returns_copy(self):
        """Test download_folders property returns a copy."""
        dd = DirectDownload(self.manager, self.folder)
        dd._download_folders.append("test_folder")
        folders = dd.download_folders
        assert folders == ["test_folder"]
        folders.append("extra")
        assert dd._download_folders == ["test_folder"]


class TestDirectDownloadCreateBatchFolder:
    """Test _create_batch_folder."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_create_batch_folder(self):
        """Test creation of timestamped batch folder."""
        dd = DirectDownload(self.manager, self.folder)
        batch_folder = dd._create_batch_folder()
        assert batch_folder.exists()
        assert batch_folder.name.startswith("download_")
        assert batch_folder.name in dd._download_folders

    def test_create_multiple_batch_folders(self):
        """Test creating multiple batch folders tracks them all."""
        dd = DirectDownload(self.manager, self.folder)
        f1 = dd._create_batch_folder()
        f2 = dd._create_batch_folder()
        assert f1.exists()
        assert f2.exists()
        assert len(dd._download_folders) == 2


class TestDirectDownloadCleanup:
    """Test cleanup method."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_cleanup_creates_folder_if_missing(self):
        """Test cleanup creates folder if it doesn't exist."""
        dd = DirectDownload(self.manager, self.folder)
        shutil.rmtree(self.folder)
        assert not self.folder.exists()
        dd._download_folders.append("old_folder")
        dd.cleanup()
        assert self.folder.exists()
        assert dd._download_folders == []

    def test_cleanup_removes_files_and_dirs(self):
        """Test cleanup removes all contents."""
        dd = DirectDownload(self.manager, self.folder)
        # Create some files and dirs
        sub = self.folder / "subdir"
        sub.mkdir()
        (sub / "file.txt").write_text("data")
        (self.folder / "loose.txt").write_text("data")
        dd._download_folders.append("subdir")

        dd.cleanup()
        assert self.folder.exists()
        assert list(self.folder.iterdir()) == []
        assert dd._download_folders == []

    def test_cleanup_handles_removal_errors(self):
        """Test cleanup handles errors during removal gracefully."""
        dd = DirectDownload(self.manager, self.folder)
        # Create a file
        f = self.folder / "file.txt"
        f.write_text("data")

        with patch.object(Path, "unlink", side_effect=PermissionError("denied")):
            dd.cleanup()  # Should not raise


class TestDirectDownloadDownload:
    """Test download slot."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_download_empty_documents(self):
        """Test download with empty document list does nothing."""
        dd = DirectDownload(self.manager, self.folder)
        dd.download([])
        assert dd._download_queue.empty()

    def test_download_queues_batch(self):
        """Test download queues the documents as a batch."""
        dd = DirectDownload(self.manager, self.folder)
        docs = [{"server_url": "http://server", "doc_id": "uuid-1"}]
        dd.download(docs)
        assert not dd._download_queue.empty()
        batch = dd._download_queue.get_nowait()
        assert batch == docs


class TestDirectDownloadGetEngine:
    """Test _get_engine method."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_get_engine_empty_url(self):
        """Test _get_engine with empty URL returns None."""
        self.manager.engines = {}
        dd = DirectDownload(self.manager, self.folder)
        assert dd._get_engine("") is None

    def test_get_engine_exact_match(self):
        """Test _get_engine exact match (first pass)."""
        engine = MockUrlTestEngine("https://server.com/nuxeo/", "admin")
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)
        result = dd._get_engine("https://server.com/nuxeo/", user="admin")
        assert result == engine

    def test_get_engine_no_user_match(self):
        """Test _get_engine matches without user."""
        engine = MockUrlTestEngine("https://server.com/nuxeo/", "admin")
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)
        result = dd._get_engine("https://server.com/nuxeo/")
        assert result == engine

    def test_get_engine_case_insensitive_user(self):
        """Test _get_engine case-insensitive user match (second pass)."""
        engine = MockUrlTestEngine("https://server.com/nuxeo/", "Admin")
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)
        # First pass won't match because "admin" != "Admin"
        # Second pass should match case-insensitively
        result = dd._get_engine("https://server.com/nuxeo/", user="admin")
        assert result == engine

    def test_get_engine_no_match(self):
        """Test _get_engine returns None when no engine matches."""
        engine = MockUrlTestEngine("https://other.com/nuxeo/", "bob")
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)
        result = dd._get_engine("https://server.com/nuxeo/", user="alice")
        assert result is None


class TestDirectDownloadGetUniquePath:
    """Test _get_unique_path method."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_unique_path_no_conflict(self):
        """Test returns same path when no conflict."""
        dd = DirectDownload(self.manager, self.folder)
        path = self.folder / "file.txt"
        assert dd._get_unique_path(path) == path

    def test_unique_path_with_conflict(self):
        """Test increments counter when file exists."""
        dd = DirectDownload(self.manager, self.folder)
        path = self.folder / "file.txt"
        path.write_text("existing")
        result = dd._get_unique_path(path)
        assert result == self.folder / "file (1).txt"

    def test_unique_path_multiple_conflicts(self):
        """Test increments counter for multiple conflicts."""
        dd = DirectDownload(self.manager, self.folder)
        (self.folder / "file.txt").write_text("a")
        (self.folder / "file (1).txt").write_text("b")
        result = dd._get_unique_path(self.folder / "file.txt")
        assert result == self.folder / "file (2).txt"


class TestDirectDownloadGetDownloadDestination:
    """Test _get_download_destination method."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_default_downloads_folder(self):
        """Test falls back to ~/Downloads when no custom folder configured."""
        dd = DirectDownload(self.manager, self.folder)
        with patch("nxdrive.direct_download.Options") as mock_opts:
            mock_opts.download_folder = None
            result = dd._get_download_destination()
            assert result == Path.home() / "Downloads"

    def test_custom_folder_writable(self):
        """Test uses custom folder when writable."""
        dd = DirectDownload(self.manager, self.folder)
        custom = self.folder / "custom_downloads"
        custom.mkdir()
        with patch("nxdrive.direct_download.Options") as mock_opts:
            mock_opts.download_folder = str(custom)
            result = dd._get_download_destination()
            assert result == custom

    def test_custom_folder_not_writable(self):
        """Test falls back when custom folder not writable."""
        dd = DirectDownload(self.manager, self.folder)
        with patch("nxdrive.direct_download.Options") as mock_opts:
            mock_opts.download_folder = "/nonexistent/path"
            result = dd._get_download_destination()
            assert result == Path.home() / "Downloads"


class TestDirectDownloadCreateZipArchive:
    """Test _create_zip_archive method."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.downloads = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        for d in [self.folder, self.downloads]:
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)

    def test_single_file_copies_directly(self):
        """Test single file is copied directly, not zipped."""
        dd = DirectDownload(self.manager, self.folder)
        batch = self.folder / "download_20250101_120000"
        batch.mkdir()
        (batch / "file.txt").write_text("hello")

        with patch.object(dd, "_get_download_destination", return_value=self.downloads):
            result = dd._create_zip_archive(batch)
            assert result is not None
            assert result.name == "file.txt"
            assert result.read_text() == "hello"

    def test_multiple_files_creates_zip(self):
        """Test multiple files create zip archive."""
        dd = DirectDownload(self.manager, self.folder)
        batch = self.folder / "download_20250101_120000"
        batch.mkdir()
        (batch / "file1.txt").write_text("a")
        (batch / "file2.txt").write_text("b")

        with patch.object(dd, "_get_download_destination", return_value=self.downloads):
            result = dd._create_zip_archive(batch)
            assert result is not None
            assert result.suffix == ".zip"
            with zipfile.ZipFile(result, "r") as zf:
                assert sorted(zf.namelist()) == ["file1.txt", "file2.txt"]

    def test_files_in_subdirs_creates_zip(self):
        """Test files with subdirectories create zip."""
        dd = DirectDownload(self.manager, self.folder)
        batch = self.folder / "download_20250101_120000"
        batch.mkdir()
        sub = batch / "subdir"
        sub.mkdir()
        (batch / "file.txt").write_text("root")
        (sub / "nested.txt").write_text("nested")

        with patch.object(dd, "_get_download_destination", return_value=self.downloads):
            result = dd._create_zip_archive(batch)
            assert result is not None
            assert result.suffix == ".zip"

    def test_archive_handles_duplicate_names(self):
        """Test zip archive handles duplicate destination names."""
        dd = DirectDownload(self.manager, self.folder)
        batch = self.folder / "download_20250101_120000"
        batch.mkdir()
        (batch / "file.txt").write_text("hello")

        # Create a pre-existing file in downloads
        (self.downloads / "file.txt").write_text("existing")

        with patch.object(dd, "_get_download_destination", return_value=self.downloads):
            result = dd._create_zip_archive(batch)
            assert result is not None
            assert result.name == "file (1).txt"

    def test_archive_returns_none_on_error(self):
        """Test returns None on exception."""
        dd = DirectDownload(self.manager, self.folder)
        batch = self.folder / "nonexistent"

        with patch.object(dd, "_get_download_destination", side_effect=OSError("fail")):
            result = dd._create_zip_archive(batch)
            assert result is None


class TestDirectDownloadCleanupBatchFolder:
    """Test _cleanup_batch_folder method (currently no-op)."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_cleanup_batch_folder_is_noop(self):
        """Test _cleanup_batch_folder is currently a no-op."""
        dd = DirectDownload(self.manager, self.folder)
        batch = self.folder / "download_20250101_120000"
        batch.mkdir()
        dd._cleanup_batch_folder(batch)
        # Batch folder should still exist since code is commented out
        assert batch.exists()


class TestDirectDownloadGetDownloadUrl:
    """Test _get_download_url method."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_file_content_url(self):
        """Test extracting URL from file:content blob."""
        dd = DirectDownload(self.manager, self.folder)
        doc = {
            "properties": {"file:content": {"data": "http://server/download/file.bin"}}
        }
        assert dd._get_download_url(doc) == "http://server/download/file.bin"

    def test_file_content_no_data(self):
        """Test file:content without data key."""
        dd = DirectDownload(self.manager, self.folder)
        doc = {"properties": {"file:content": {"name": "test.txt"}}}
        assert dd._get_download_url(doc) is None

    def test_file_content_not_dict(self):
        """Test file:content is not a dict."""
        dd = DirectDownload(self.manager, self.folder)
        doc = {"properties": {"file:content": "string_val"}}
        assert dd._get_download_url(doc) is None

    def test_note_document_returns_none(self):
        """Test Note documents return None."""
        dd = DirectDownload(self.manager, self.folder)
        doc = {
            "type": "Note",
            "properties": {"note:note": "<p>Hello</p>"},
        }
        assert dd._get_download_url(doc) is None

    def test_no_properties(self):
        """Test document with no properties."""
        dd = DirectDownload(self.manager, self.folder)
        doc = {"properties": {}}
        assert dd._get_download_url(doc) is None

    def test_no_file_content_not_note(self):
        """Test regular document without file:content returns None."""
        dd = DirectDownload(self.manager, self.folder)
        doc = {"type": "CustomType", "properties": {}}
        assert dd._get_download_url(doc) is None


class TestDirectDownloadFile:
    """Test _download_file method."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_download_file_relative_url(self):
        """Test downloading file with relative URL."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        engine.remote.client.host = "https://server.com"
        engine.remote.verification_needed = False
        resp = Mock()
        resp.content = b"file_content"
        engine.remote.client.request.return_value = resp

        dd._download_file(
            engine,
            "https://server.com",
            "nxfile/default/uuid/file:content/test.txt",
            "test.txt",
            self.folder,
        )

        target = self.folder / "test.txt"
        assert target.exists()
        assert target.read_bytes() == b"file_content"

    def test_download_file_absolute_url(self):
        """Test downloading file with absolute URL."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        engine.remote.client.host = "https://server.com"
        engine.remote.verification_needed = True
        resp = Mock()
        resp.content = b"data"
        engine.remote.client.request.return_value = resp

        dd._download_file(
            engine,
            "https://server.com",
            "https://server.com/download/file.bin",
            "file.bin",
            self.folder,
        )
        assert (self.folder / "file.bin").read_bytes() == b"data"

    def test_download_file_raises_on_error(self):
        """Test _download_file raises when request fails."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        engine.remote.client.host = "https://server.com"
        engine.remote.client.request.side_effect = ConnectionError("timeout")

        with pytest.raises(ConnectionError):
            dd._download_file(
                engine, "https://server.com", "/path", "f.txt", self.folder
            )


class TestDirectDownloadFolder:
    """Test _download_folder method."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_download_folder_creates_local_folder(self):
        """Test folder download creates local directory."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        engine.remote.query.return_value = {"entries": []}

        with patch.object(dd, "_get_children", return_value=[]):
            dd._download_folder(engine, "folder-uid", "MyFolder", self.folder)
            assert (self.folder / "MyFolder").is_dir()

    def test_download_folder_with_files(self):
        """Test folder download with file children."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        engine.server_url = "https://server.com"

        children = [
            {
                "uid": "file-uid",
                "facets": [],
                "properties": {
                    "dc:title": "report.pdf",
                    "file:content": {"data": "https://server.com/dl/report.pdf"},
                },
            }
        ]

        with (
            patch.object(dd, "_get_children", return_value=children),
            patch.object(dd, "_download_file") as mock_dl,
        ):
            dd._download_folder(engine, "folder-uid", "TestFolder", self.folder)
            mock_dl.assert_called_once()

    def test_download_folder_with_subfolders(self):
        """Test folder download recursively handles subfolders."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()

        subfolder_child = {
            "uid": "sub-uid",
            "facets": ["Folderish"],
            "properties": {"dc:title": "SubFolder"},
        }

        with patch.object(
            dd,
            "_get_children",
            side_effect=[
                [subfolder_child],  # Parent folder children
                [],  # Subfolder children (empty)
            ],
        ):
            dd._download_folder(engine, "folder-uid", "Parent", self.folder)
            assert (self.folder / "Parent").is_dir()
            assert (self.folder / "Parent" / "SubFolder").is_dir()

    def test_download_folder_handles_children_error(self):
        """Test folder download handles error fetching children."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()

        with patch.object(dd, "_get_children", side_effect=RuntimeError("API error")):
            dd._download_folder(engine, "folder-uid", "ErrFolder", self.folder)
            assert (self.folder / "ErrFolder").is_dir()


class TestDirectDownloadGetChildren:
    """Test _get_children method."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_get_children_fetches_full_docs(self):
        """Test _get_children fetches each child individually."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        engine.remote.query.return_value = {
            "entries": [{"uid": "child-1"}, {"uid": "child-2"}]
        }
        full_doc1 = {"uid": "child-1", "properties": {"file:content": {"length": 100}}}
        full_doc2 = {"uid": "child-2", "properties": {"file:content": {"length": 200}}}
        engine.remote.fetch.side_effect = [full_doc1, full_doc2]

        result = dd._get_children(engine, "parent-id")
        assert len(result) == 2
        assert result[0] == full_doc1
        assert result[1] == full_doc2

    def test_get_children_fallback_on_fetch_error(self):
        """Test fallback to query result if individual fetch fails."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        entry = {"uid": "child-1"}
        engine.remote.query.return_value = {"entries": [entry]}
        engine.remote.fetch.side_effect = RuntimeError("network")

        result = dd._get_children(engine, "parent-id")
        assert len(result) == 1
        assert result[0] == entry

    def test_get_children_empty_uid_entry(self):
        """Test entries with empty uid are included as-is."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        entry = {"uid": "", "name": "orphan"}
        engine.remote.query.return_value = {"entries": [entry]}

        result = dd._get_children(engine, "parent-id")
        assert len(result) == 1
        assert result[0] == entry


class TestDirectDownloadCalculateFolderSize:
    """Test _calculate_folder_size method."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_empty_folder(self):
        """Test empty folder returns zeros."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()

        with patch.object(dd, "_get_children", return_value=[]):
            size, folders, files = dd._calculate_folder_size(engine, "folder-id")
            assert size == 0
            assert folders == 0
            assert files == 0

    def test_folder_with_files(self):
        """Test folder with files returns correct totals."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        children = [
            {
                "uid": "f1",
                "facets": [],
                "properties": {"file:content": {"length": "1000"}},
            },
            {
                "uid": "f2",
                "facets": [],
                "properties": {"file:content": {"length": "2000"}},
            },
        ]

        with patch.object(dd, "_get_children", return_value=children):
            size, folders, files = dd._calculate_folder_size(engine, "folder-id")
            assert size == 3000
            assert folders == 0
            assert files == 2

    def test_folder_with_subfolders(self):
        """Test folder with nested subfolders."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()

        parent_children = [
            {"uid": "sub-1", "facets": ["Folderish"], "properties": {}},
        ]
        sub_children = [
            {
                "uid": "file-1",
                "facets": [],
                "properties": {"file:content": {"length": "500"}},
            },
        ]

        with patch.object(
            dd, "_get_children", side_effect=[parent_children, sub_children]
        ):
            size, folders, files = dd._calculate_folder_size(engine, "folder-id")
            assert size == 500
            assert folders == 1
            assert files == 1

    def test_folder_size_handles_error(self):
        """Test returns zeros on error."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()

        with patch.object(dd, "_get_children", side_effect=RuntimeError("fail")):
            size, folders, files = dd._calculate_folder_size(engine, "folder-id")
            assert size == 0
            assert folders == 0
            assert files == 0

    def test_file_without_content(self):
        """Test file without file:content."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        children = [{"uid": "f1", "facets": [], "properties": {}}]

        with patch.object(dd, "_get_children", return_value=children):
            size, folders, files = dd._calculate_folder_size(engine, "folder-id")
            assert size == 0
            assert files == 1


class TestDirectDownloadProcessDownload:
    """Test _process_download method."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_process_download_no_engine(self):
        """Test _process_download raises when no engine found."""
        dd = DirectDownload(self.manager, self.folder)
        doc = {"server_url": "https://unknown.com", "doc_id": "uuid-1"}

        with patch.object(dd, "_get_engine", return_value=None):
            with pytest.raises(RuntimeError, match="No engine found"):
                dd._process_download(doc, self.folder)

    def test_process_download_doc_not_found(self):
        """Test _process_download raises when document not found."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        engine.remote.get_info.return_value = None
        doc = {"server_url": "https://server.com", "doc_id": "uuid-1"}

        with patch.object(dd, "_get_engine", return_value=engine):
            with pytest.raises(
                RuntimeError, match="Failed to get document information"
            ):
                dd._process_download(doc, self.folder)

    def test_process_download_file_success(self):
        """Test _process_download for a regular file."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        doc_info = Mock()
        doc_info.folderish = False
        doc_info.name = "report.pdf"
        blob = Mock()
        blob.name = "report.pdf"
        doc_info.get_blob.return_value = blob
        engine.remote.get_info.return_value = doc_info

        doc = {"server_url": "https://server.com", "doc_id": "uuid-1"}

        with (
            patch.object(dd, "_get_engine", return_value=engine),
            patch.object(dd, "_download_file") as mock_dl,
        ):
            dd._process_download(doc, self.folder)
            mock_dl.assert_called_once()

    def test_process_download_folder_success(self):
        """Test _process_download for a folder."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        doc_info = Mock()
        doc_info.folderish = True
        doc_info.name = "MyFolder"
        engine.remote.get_info.return_value = doc_info

        doc = {"server_url": "https://server.com", "doc_id": "uuid-1"}

        with (
            patch.object(dd, "_get_engine", return_value=engine),
            patch.object(dd, "_download_folder") as mock_dl,
        ):
            dd._process_download(doc, self.folder)
            mock_dl.assert_called_once()

    def test_process_download_uses_provided_filename(self):
        """Test _process_download uses filename from doc dict."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        doc_info = Mock()
        doc_info.folderish = False
        doc_info.name = "server_name.txt"
        blob = Mock()
        blob.name = "file.txt"
        doc_info.get_blob.return_value = blob
        engine.remote.get_info.return_value = doc_info

        doc = {
            "server_url": "https://server.com",
            "doc_id": "uuid-1",
            "filename": "custom.txt",
            "download_url": "nxfile/default/uuid-1/file:content/file.txt",
        }

        with (
            patch.object(dd, "_get_engine", return_value=engine),
            patch.object(dd, "_download_file"),
        ):
            dd._process_download(doc, self.folder)

    def test_process_download_get_info_fails(self):
        """Test error when get_info raises."""
        dd = DirectDownload(self.manager, self.folder)
        engine = Mock()
        engine.remote.get_info.side_effect = ConnectionError("timeout")

        doc = {"server_url": "https://server.com", "doc_id": "uuid-1"}

        with patch.object(dd, "_get_engine", return_value=engine):
            with pytest.raises(
                RuntimeError, match="Failed to get document information"
            ):
                dd._process_download(doc, self.folder)


class TestDirectDownloadProcessBatch:
    """Test _process_batch method."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_process_batch_success(self):
        """Test _process_batch with successful downloads."""
        dd = DirectDownload(self.manager, self.folder)

        docs = [
            {
                "server_url": "https://server.com",
                "doc_id": "uuid-1",
                "filename": "a.txt",
            },
            {
                "server_url": "https://server.com",
                "doc_id": "uuid-2",
                "filename": "b.txt",
            },
        ]

        with (
            patch.object(dd, "_create_download_record", return_value=1),
            patch.object(dd, "_update_download_status"),
            patch.object(dd, "_process_download"),
            patch.object(
                dd, "_create_zip_archive", return_value=Path("/tmp/archive.zip")
            ),
            patch.object(dd, "_update_download_path"),
        ):
            dd._process_batch(docs)

    def test_process_batch_with_failure(self):
        """Test _process_batch handles download failures."""
        dd = DirectDownload(self.manager, self.folder)

        docs = [
            {
                "server_url": "https://server.com",
                "doc_id": "uuid-1",
                "filename": "a.txt",
            },
        ]

        with (
            patch.object(dd, "_create_download_record", return_value=1),
            patch.object(dd, "_update_download_status"),
            patch.object(dd, "_process_download", side_effect=RuntimeError("fail")),
            patch.object(dd, "_create_zip_archive", return_value=None),
        ):
            dd._process_batch(docs)

    def test_process_batch_no_record_uid(self):
        """Test _process_batch when record creation returns None."""
        dd = DirectDownload(self.manager, self.folder)

        docs = [
            {"server_url": "https://server.com", "doc_id": "uuid-1"},
        ]

        with (
            patch.object(dd, "_create_download_record", return_value=None),
            patch.object(dd, "_process_download"),
            patch.object(dd, "_create_zip_archive", return_value=None),
        ):
            dd._process_batch(docs)

    def test_process_batch_selected_items_fallback(self):
        """Test selected items use doc_id when filename is empty."""
        dd = DirectDownload(self.manager, self.folder)

        docs = [
            {"server_url": "https://server.com", "doc_id": "uuid-1", "filename": ""},
        ]

        with (
            patch.object(dd, "_create_download_record", return_value=None),
            patch.object(dd, "_process_download"),
            patch.object(dd, "_create_zip_archive", return_value=None),
        ):
            dd._process_batch(docs)


class TestDirectDownloadDBOperations:
    """Test database operations methods."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_create_download_record_no_engine(self):
        """Test returns None when no engine found."""
        self.manager.engines = {}
        dd = DirectDownload(self.manager, self.folder)
        doc = {"server_url": "https://server.com", "doc_id": "uuid-1"}

        with patch.object(dd, "_get_engine", return_value=None):
            result = dd._create_download_record(doc)
            assert result is None

    def test_create_download_record_no_dao(self):
        """Test returns None when engine has no DAO."""
        engine = Mock()
        engine.dao = None
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)
        doc = {"server_url": "https://server.com", "doc_id": "uuid-1"}

        with patch.object(dd, "_get_engine", return_value=engine):
            result = dd._create_download_record(doc)
            assert result is None

    def test_create_download_record_file_success(self):
        """Test creates record for a file."""
        engine = Mock()
        engine.uid = "engine-1"
        engine.dao.save_direct_download.return_value = 42
        engine.remote.fetch.return_value = {
            "facets": [],
            "properties": {
                "dc:title": "test.pdf",
                "file:content": {"length": "1024"},
            },
        }
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)
        doc = {"server_url": "https://server.com", "doc_id": "uuid-1"}

        with patch.object(dd, "_get_engine", return_value=engine):
            result = dd._create_download_record(doc, batch_id="batch-1")
            assert result == 42
            engine.dao.save_direct_download.assert_called_once()

    def test_create_download_record_folder(self):
        """Test creates record for a folder."""
        engine = Mock()
        engine.uid = "engine-1"
        engine.dao.save_direct_download.return_value = 10
        engine.remote.fetch.return_value = {
            "facets": ["Folderish"],
            "properties": {"dc:title": "FolderName"},
        }
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)
        doc = {"server_url": "https://server.com", "doc_id": "uuid-1"}

        with (
            patch.object(dd, "_get_engine", return_value=engine),
            patch.object(dd, "_calculate_folder_size", return_value=(5000, 2, 10)),
        ):
            result = dd._create_download_record(doc)
            assert result == 10

    def test_create_download_record_fetch_fails(self):
        """Test record created even if fetch fails (uses defaults)."""
        engine = Mock()
        engine.uid = "engine-1"
        engine.dao.save_direct_download.return_value = 5
        engine.remote.fetch.side_effect = RuntimeError("network")
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)
        doc = {"server_url": "https://server.com", "doc_id": "uuid-1"}

        with patch.object(dd, "_get_engine", return_value=engine):
            result = dd._create_download_record(doc)
            assert result == 5

    def test_create_download_record_exception(self):
        """Test returns None on unhandled error."""
        self.manager.engines = {}
        dd = DirectDownload(self.manager, self.folder)
        doc = {"server_url": "https://server.com", "doc_id": "uuid-1"}

        with patch.object(dd, "_get_engine", side_effect=Exception("boom")):
            result = dd._create_download_record(doc)
            assert result is None

    def test_update_download_status_success(self):
        """Test updating download status."""
        engine = Mock()
        record = Mock()
        engine.dao.get_direct_download.return_value = record
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)

        dd._update_download_status(
            1, DirectDownloadStatus.COMPLETED, download_path="/dl"
        )
        engine.dao.update_direct_download_status.assert_called_once()
        assert record.download_path == "/dl"

    def test_update_download_status_no_record(self):
        """Test no error when record not found."""
        engine = Mock()
        engine.dao.get_direct_download.return_value = None
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)

        dd._update_download_status(999, DirectDownloadStatus.FAILED)

    def test_update_download_status_exception(self):
        """Test handles exception."""
        engine = Mock()
        engine.dao.get_direct_download.side_effect = RuntimeError("db error")
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)

        dd._update_download_status(1, DirectDownloadStatus.FAILED)

    def test_update_download_path_success(self):
        """Test updating download path."""
        engine = Mock()
        record = Mock()
        engine.dao.get_direct_download.return_value = record
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)

        dd._update_download_path(1, "/new/path", "archive.zip")
        assert record.download_path == "/new/path"
        assert record.zip_file == "archive.zip"
        engine.dao.update_direct_download.assert_called_once_with(record)

    def test_update_download_path_no_record(self):
        """Test no error when record not found."""
        engine = Mock()
        engine.dao.get_direct_download.return_value = None
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)

        dd._update_download_path(999, "/path")

    def test_update_download_path_exception(self):
        """Test handles exception."""
        engine = Mock()
        engine.dao.get_direct_download.side_effect = RuntimeError("db error")
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)

        dd._update_download_path(1, "/path")

    def test_update_download_progress_success(self):
        """Test updating download progress."""
        engine = Mock()
        record = Mock()
        engine.dao.get_direct_download.return_value = record
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)

        dd._update_download_progress(1, 500, 1000)
        engine.dao.update_direct_download_progress.assert_called_once_with(
            1, 500, 1000, 50.0
        )

    def test_update_download_progress_zero_total(self):
        """Test progress with zero total bytes."""
        engine = Mock()
        record = Mock()
        engine.dao.get_direct_download.return_value = record
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)

        dd._update_download_progress(1, 0, 0)
        engine.dao.update_direct_download_progress.assert_called_once_with(1, 0, 0, 0.0)

    def test_update_download_progress_no_record(self):
        """Test no error when record not found."""
        engine = Mock()
        engine.dao.get_direct_download.return_value = None
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)

        dd._update_download_progress(999, 100, 200)

    def test_update_download_progress_exception(self):
        """Test handles exception."""
        engine = Mock()
        engine.dao.get_direct_download.side_effect = RuntimeError("db error")
        self.manager.engines = {"uid1": engine}
        dd = DirectDownload(self.manager, self.folder)

        dd._update_download_progress(1, 100, 200)


class TestDirectDownloadStop:
    """Test stop method."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_stop_sets_flag(self):
        """Test stop sets _stop flag."""
        dd = DirectDownload(self.manager, self.folder)
        dd._stop = False
        dd.stop()
        assert dd._stop is True


class TestDirectDownloadExecute:
    """Test _execute main loop."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_execute_processes_queue_item(self):
        """Test _execute processes items from the download queue."""
        dd = DirectDownload(self.manager, self.folder)
        batch = [{"doc_id": "abc", "server_url": "https://example.com"}]
        dd._download_queue.put(batch)
        dd._process_batch = Mock()

        # Run _execute once then stop
        call_count = 0

        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                dd._stop = True

        dd._interact = side_effect
        dd._execute()
        dd._process_batch.assert_called_once_with(batch)

    def test_execute_handles_exception(self):
        """Test _execute handles exceptions in processing."""
        dd = DirectDownload(self.manager, self.folder)
        batch = [{"doc_id": "abc"}]
        dd._download_queue.put(batch)
        dd._process_batch = Mock(side_effect=RuntimeError("test error"))

        call_count = 0

        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                dd._stop = True

        dd._interact = side_effect
        # Should not raise
        dd._execute()

    def test_execute_empty_queue(self):
        """Test _execute skips processing when queue is empty."""
        dd = DirectDownload(self.manager, self.folder)
        dd._process_batch = Mock()

        call_count = 0

        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                dd._stop = True

        dd._interact = side_effect
        dd._execute()
        dd._process_batch.assert_not_called()


class TestDirectDownloadGetDownloadDestinationFallback:
    """Test _get_download_destination fallback when Downloads dir doesn't exist."""

    def setup_method(self):
        self.manager = Mock()
        self.folder = Path(tempfile.mkdtemp())
        self.manager.directDownload = Mock()
        self.manager.engines = {}

    def teardown_method(self):
        if self.folder.exists():
            shutil.rmtree(self.folder, ignore_errors=True)

    def test_creates_downloads_dir_if_missing(self, tmp_path):
        """Test creates ~/Downloads if it doesn't exist."""
        dd = DirectDownload(self.manager, self.folder)
        with (
            patch("nxdrive.direct_download.Options") as mock_opts,
            patch("nxdrive.direct_download.Path") as mock_path_cls,
        ):
            mock_opts.download_folder = None
            mock_home = Mock()
            mock_path_cls.home.return_value = mock_home
            mock_downloads = Mock()
            mock_home.__truediv__ = Mock(return_value=mock_downloads)
            mock_downloads.exists.return_value = False
            mock_downloads.mkdir = Mock()

            result = dd._get_download_destination()

            mock_downloads.mkdir.assert_called_once_with(parents=True, exist_ok=True)
            assert result == mock_downloads


class TestDirectDownloadStatusEnum:
    """Test DirectDownloadStatus enum values."""

    def test_status_values(self):
        assert DirectDownloadStatus.PENDING.value == 0
        assert DirectDownloadStatus.IN_PROGRESS.value == 1
        assert DirectDownloadStatus.COMPLETED.value == 2
        assert DirectDownloadStatus.FAILED.value == 3
        assert DirectDownloadStatus.PAUSED.value == 4
        assert DirectDownloadStatus.CANCELLED.value == 5

    def test_all_statuses(self):
        assert len(DirectDownloadStatus) == 6


class TestDirectDownloadRecord:
    """Test DirectDownload dataclass from objects.py."""

    def test_create_record(self):
        now = datetime.now(timezone.utc)
        record = DirectDownloadRecord(
            uid=1,
            doc_uid="uuid-123",
            doc_name="test.pdf",
            doc_size=1024,
            download_path="/downloads/test.pdf",
            server_url="https://server.com",
            status=DirectDownloadStatus.PENDING,
            bytes_downloaded=0,
            total_bytes=1024,
            progress_percent=0.0,
            created_at=now,
            started_at=None,
            completed_at=None,
            is_folder=False,
            folder_count=0,
            file_count=1,
            retry_count=0,
            last_error=None,
            engine="engine-1",
            zip_file=None,
            selected_items="test.pdf",
        )
        assert record.uid == 1
        assert record.doc_name == "test.pdf"
        assert record.status == DirectDownloadStatus.PENDING
        assert record.is_folder is False
        assert record.file_count == 1

    def test_record_with_folder(self):
        now = datetime.now(timezone.utc)
        record = DirectDownloadRecord(
            uid=2,
            doc_uid="uuid-456",
            doc_name="MyFolder",
            doc_size=5000,
            download_path=None,
            server_url="https://server.com",
            status=DirectDownloadStatus.IN_PROGRESS,
            bytes_downloaded=1000,
            total_bytes=5000,
            progress_percent=20.0,
            created_at=now,
            started_at=now,
            completed_at=None,
            is_folder=True,
            folder_count=3,
            file_count=10,
            retry_count=0,
            last_error=None,
            engine="engine-1",
            zip_file="download_20250101_120000",
            selected_items="file1.txt, file2.txt",
        )
        assert record.is_folder is True
        assert record.folder_count == 3
        assert record.progress_percent == 20.0


class TestParseDownloadProtocol:
    """Test parse_download_protocol and _parse_single_document_path from utils.py."""

    def test_single_doc_super_simple_format(self):
        """Test super-simple format: https/server/UUID."""
        from nxdrive.utils import parse_download_protocol

        url = "nxdrive://direct-download/https/drive.nuxeocloud.com/3eebfb90-4e2c-4aa9-bf3f-b657c02572e1"
        result = parse_download_protocol({}, url)
        assert result["command"] == "download_direct"
        assert len(result["documents"]) == 1
        doc = result["documents"][0]
        assert doc["server_url"] == "https://drive.nuxeocloud.com/nuxeo/"
        assert doc["doc_id"] == "3eebfb90-4e2c-4aa9-bf3f-b657c02572e1"

    def test_batch_download(self):
        """Test batch download with multiple UUIDs."""
        from nxdrive.utils import parse_download_protocol

        url = (
            "nxdrive://direct-download/"
            "https/server.com/11111111-1111-1111-1111-111111111111"
            " || 22222222-2222-2222-2222-222222222222"
            " || 33333333-3333-3333-3333-333333333333"
        )
        result = parse_download_protocol({}, url)
        assert len(result["documents"]) == 3
        # First doc has server URL
        assert result["documents"][0]["server_url"] == "https://server.com/nuxeo/"
        # Subsequent docs inherit server URL
        assert result["documents"][1]["server_url"] == "https://server.com/nuxeo/"
        assert result["documents"][2]["server_url"] == "https://server.com/nuxeo/"

    def test_simplified_format_with_nxdocid(self):
        """Test legacy format: https/server/nuxeo/nxdocid/UUID."""
        from nxdrive.utils import parse_download_protocol

        url = "nxdrive://direct-download/https/server.com/nuxeo/nxdocid/11111111-1111-1111-1111-111111111111"
        result = parse_download_protocol({}, url)
        assert len(result["documents"]) == 1
        doc = result["documents"][0]
        assert doc["doc_id"] == "11111111-1111-1111-1111-111111111111"

    def test_full_format_legacy(self):
        """Test full legacy format with user/repo/downloadUrl."""
        from nxdrive.utils import parse_download_protocol

        url = (
            "nxdrive://direct-download/"
            "https/server.com/nuxeo/user/admin/repo/default/"
            "nxdocid/11111111-1111-1111-1111-111111111111/"
            "filename/test.pdf/downloadUrl/nxfile/default/uid/file:content/test.pdf"
        )
        result = parse_download_protocol({}, url)
        assert len(result["documents"]) == 1
        doc = result["documents"][0]
        assert doc["user"] == "admin"
        assert doc["repo"] == "default"
        assert doc["filename"] == "test.pdf"

    def test_empty_url(self):
        """Test URL with no valid documents."""
        from nxdrive.utils import parse_download_protocol

        url = "nxdrive://direct-download/"
        result = parse_download_protocol({}, url)
        assert result["documents"] == []

    def test_uuid_without_server(self):
        """Test bare UUID without server URL from first doc."""
        from nxdrive.utils import _parse_single_document_path

        result = _parse_single_document_path("11111111-1111-1111-1111-111111111111")
        assert result is None

    def test_uuid_with_server(self):
        """Test bare UUID with server URL from previous document."""
        from nxdrive.utils import _parse_single_document_path

        result = _parse_single_document_path(
            "11111111-1111-1111-1111-111111111111",
            server_url="https://server.com/nuxeo/",
        )
        assert result is not None
        assert result["doc_id"] == "11111111-1111-1111-1111-111111111111"
        assert result["server_url"] == "https://server.com/nuxeo/"

    def test_invalid_path(self):
        """Test completely invalid path."""
        from nxdrive.utils import _parse_single_document_path

        result = _parse_single_document_path("totally-invalid-gibberish")
        assert result is None

    def test_simplified_without_nuxeo_prefix(self):
        """Test simplified format where server doesn't include /nuxeo."""
        from nxdrive.utils import _parse_single_document_path

        result = _parse_single_document_path(
            "https/server.com/nxdocid/11111111-1111-1111-1111-111111111111"
        )
        assert result is not None
        assert result["server_url"] == "https://server.com/nuxeo/"

    def test_full_format_without_nuxeo_prefix(self):
        """Test full format where server doesn't include /nuxeo."""
        from nxdrive.utils import _parse_single_document_path

        result = _parse_single_document_path(
            "https/server.com/user/admin/repo/default/"
            "nxdocid/11111111-1111-1111-1111-111111111111/"
            "filename/test.pdf/downloadUrl/nxfile/default/uid/file:content/test.pdf"
        )
        assert result is not None
        assert result["server_url"] == "https://server.com/nuxeo/"

    def test_batch_with_empty_parts(self):
        """Test batch URL with empty parts after split."""
        from nxdrive.utils import parse_download_protocol

        url = (
            "nxdrive://direct-download/"
            "https/server.com/11111111-1111-1111-1111-111111111111"
            " ||  || 22222222-2222-2222-2222-222222222222"
        )
        result = parse_download_protocol({}, url)
        assert len(result["documents"]) == 2


class TestParseProtocolUrlDirectDownload:
    """Test parse_protocol_url for direct-download URLs."""

    def test_full_parsing_flow(self):
        """Test the complete parse_protocol_url flow for direct-download."""
        from nxdrive.utils import parse_protocol_url

        url = "nxdrive://direct-download/https/server.com/11111111-1111-1111-1111-111111111111"
        result = parse_protocol_url(url)
        assert result["command"] == "download_direct"
        assert len(result["documents"]) == 1
