"""Unit tests for nxdrive.nuxeo.direct_download module."""

from pathlib import Path
from unittest.mock import Mock, patch


class TestDirectDownloadGetDownloadUrl:
    def _make_dd(self):
        from nxdrive.nuxeo.direct_download import DirectDownload

        with patch.object(DirectDownload, "__init__", return_value=None):
            dd = DirectDownload.__new__(DirectDownload)
        return dd

    def test_file_content_data(self):
        dd = self._make_dd()
        doc = {
            "properties": {
                "file:content": {
                    "data": "nxfile/default/doc-1/file:content/test.pdf",
                    "name": "test.pdf",
                }
            },
            "type": "File",
        }
        result = dd._get_download_url(doc)
        assert result == "nxfile/default/doc-1/file:content/test.pdf"

    def test_files_files_fallback(self):
        dd = self._make_dd()
        doc = {
            "properties": {
                "file:content": None,
                "files:files": [
                    {
                        "file": {
                            "data": "nxfile/default/doc-1/files:files/0/file/att.docx",
                            "name": "att.docx",
                        }
                    }
                ],
            },
            "type": "File",
        }
        result = dd._get_download_url(doc)
        assert result == "nxfile/default/doc-1/files:files/0/file/att.docx"

    def test_no_content_returns_none(self):
        dd = self._make_dd()
        doc = {
            "properties": {},
            "type": "File",
        }
        result = dd._get_download_url(doc)
        assert result is None

    def test_note_with_content_returns_none(self):
        dd = self._make_dd()
        doc = {
            "properties": {
                "note:note": "<p>Hello</p>",
            },
            "type": "Note",
        }
        result = dd._get_download_url(doc)
        assert result is None

    def test_note_without_content_returns_none(self):
        dd = self._make_dd()
        doc = {
            "properties": {
                "note:note": "",
            },
            "type": "Note",
        }
        result = dd._get_download_url(doc)
        assert result is None


class TestDirectDownloadGetDestination:
    def _make_dd(self):
        from nxdrive.nuxeo.direct_download import DirectDownload

        with patch.object(DirectDownload, "__init__", return_value=None):
            dd = DirectDownload.__new__(DirectDownload)
        return dd

    def test_returns_downloads_folder(self):
        dd = self._make_dd()
        with patch("nxdrive.nuxeo.direct_download.Options") as mock_opts:
            mock_opts.download_folder = ""
            result = dd._get_download_destination()
        assert result == Path.home() / "Downloads"

    def test_configured_folder_used_when_exists(self, tmp_path):
        dd = self._make_dd()
        with patch("nxdrive.nuxeo.direct_download.Options") as mock_opts:
            mock_opts.download_folder = str(tmp_path)
            result = dd._get_download_destination()
        assert result == tmp_path


class TestDirectDownloadGetChildren:
    def _make_dd(self):
        from nxdrive.nuxeo.direct_download import DirectDownload

        with patch.object(DirectDownload, "__init__", return_value=None):
            dd = DirectDownload.__new__(DirectDownload)
        return dd

    def test_single_page(self):
        dd = self._make_dd()
        engine = Mock()
        engine.remote.execute.return_value = {
            "entries": [
                {"uid": "c1", "properties": {"dc:title": "Child1"}, "facets": []},
                {"uid": "c2", "properties": {"dc:title": "Child2"}, "facets": []},
            ]
        }
        children = dd._get_children(engine, "parent-1")
        assert len(children) == 2

    def test_multiple_pages(self):
        dd = self._make_dd()
        engine = Mock()
        # First page returns full page_size (1000), second returns less
        page1 = [{"uid": f"c{i}"} for i in range(1000)]
        page2 = [{"uid": "last"}]
        engine.remote.execute.side_effect = [
            {"entries": page1},
            {"entries": page2},
        ]
        children = dd._get_children(engine, "parent-1")
        assert len(children) == 1001

    def test_empty_folder(self):
        dd = self._make_dd()
        engine = Mock()
        engine.remote.execute.return_value = {"entries": []}
        children = dd._get_children(engine, "parent-1")
        assert children == []


class TestDirectDownloadCalculateFolderSize:
    def _make_dd(self):
        from nxdrive.nuxeo.direct_download import DirectDownload

        with patch.object(DirectDownload, "__init__", return_value=None):
            dd = DirectDownload.__new__(DirectDownload)
        return dd

    def test_files_only(self):
        dd = self._make_dd()
        engine = Mock()
        children = [
            {
                "uid": "f1",
                "facets": [],
                "properties": {"file:content": {"length": "1024"}},
            },
            {
                "uid": "f2",
                "facets": [],
                "properties": {"file:content": {"length": "2048"}},
            },
        ]
        dd._get_children = Mock(return_value=children)
        total, folders, files = dd._calculate_folder_size(engine, "folder-1")
        assert total == 3072
        assert folders == 0
        assert files == 2

    def test_subfolder_recursive(self):
        dd = self._make_dd()
        engine = Mock()

        # Main folder has 1 file + 1 subfolder
        main_children = [
            {
                "uid": "f1",
                "facets": [],
                "properties": {"file:content": {"length": "500"}},
            },
            {
                "uid": "sub1",
                "facets": ["Folderish"],
                "properties": {},
            },
        ]
        # Subfolder has 1 file
        sub_children = [
            {
                "uid": "f2",
                "facets": [],
                "properties": {"file:content": {"length": "300"}},
            },
        ]

        dd._get_children = Mock(side_effect=[main_children, sub_children])
        total, folders, files = dd._calculate_folder_size(engine, "folder-1")
        assert total == 800
        assert folders == 1
        assert files == 2

    def test_file_without_content(self):
        dd = self._make_dd()
        engine = Mock()
        children = [
            {
                "uid": "f1",
                "facets": [],
                "properties": {},
            },
        ]
        dd._get_children = Mock(return_value=children)
        # get_info should be tried for fallback
        engine.remote.get_info.return_value = None
        total, folders, files = dd._calculate_folder_size(engine, "folder-1")
        assert total == 0
        assert files == 1


class TestDirectDownloadCreateRecord:
    def _make_dd(self):
        from nxdrive.nuxeo.direct_download import DirectDownload

        with patch.object(DirectDownload, "__init__", return_value=None):
            dd = DirectDownload.__new__(DirectDownload)
        return dd

    def test_returns_none_when_no_engine(self):
        dd = self._make_dd()
        dd._get_engine = Mock(return_value=None)
        result = dd._create_download_record({"server_url": "http://s", "doc_id": "d1"})
        assert result is None

    def test_creates_record_for_file(self):
        dd = self._make_dd()
        engine = Mock()
        engine.uid = "eng-1"
        engine.dao.save_direct_download.return_value = 42
        engine.remote.fetch.return_value = {
            "facets": [],
            "properties": {
                "dc:title": "TestFile",
                "file:content": {"length": "2048"},
            },
        }
        dd._get_engine = Mock(return_value=engine)
        result = dd._create_download_record(
            {"server_url": "http://s", "doc_id": "d1", "user": "admin"}
        )
        assert result == 42
        engine.dao.update_direct_download.assert_called_once()
