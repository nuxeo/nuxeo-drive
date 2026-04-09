from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pytest

from nxdrive.client.alfresco.client import AlfrescoClientError
from nxdrive.client.alfresco_remote import AlfrescoRemote, _alfresco_permissions


def _remote() -> AlfrescoRemote:
    return AlfrescoRemote(
        "https://alfresco.local",
        "alice",
        "device-1",
        "1.0",
        password="secret",
    )


def test_upload_folder_type_rejects_empty_name() -> None:
    remote = _remote()
    remote._client._request = Mock()  # noqa: SLF001

    with pytest.raises(ValueError, match="Folder name cannot be empty"):
        remote.upload_folder_type("parent-id", {"name": ""})

    remote._client._request.assert_not_called()  # noqa: SLF001


def test_upload_folder_type_rejects_whitespace_only_name() -> None:
    remote = _remote()
    remote._client._request = Mock()  # noqa: SLF001

    with pytest.raises(ValueError, match="Folder name cannot be empty"):
        remote.upload_folder_type("parent-id", {"name": "   "})

    remote._client._request.assert_not_called()  # noqa: SLF001


def test_remote_exposes_client_repository_compatibility() -> None:
    remote = _remote()

    assert remote.client is remote._client  # noqa: SLF001
    assert getattr(remote.client, "repository") == remote.repository


def test_get_fs_children_fetches_all_pages() -> None:
    remote = _remote()
    remote._client.list_nodes = Mock(  # noqa: SLF001
        side_effect=[
            {
                "list": {
                    "entries": [
                        {
                            "entry": {
                                "id": "doc-1",
                                "name": "a.txt",
                                "isFolder": False,
                                "parentId": "parent",
                                "path": {"name": "/"},
                            }
                        }
                    ],
                    "pagination": {"count": 1, "hasMoreItems": True},
                }
            },
            {
                "list": {
                    "entries": [
                        {
                            "entry": {
                                "id": "doc-2",
                                "name": "b.txt",
                                "isFolder": False,
                                "parentId": "parent",
                                "path": {"name": "/"},
                            }
                        }
                    ],
                    "pagination": {"count": 1, "hasMoreItems": False},
                }
            },
        ]
    )

    children = remote.get_fs_children("parent", filtered=False)

    assert [child.uid for child in children] == ["doc-1", "doc-2"]
    assert remote._client.list_nodes.call_count == 2  # noqa: SLF001


def test_node_mapping_disables_scroll_descendants_for_alfresco() -> None:
    remote = _remote()

    info = remote._node_to_fs_item(  # noqa: SLF001
        {
            "id": "folder-1",
            "name": "Folder",
            "isFolder": True,
            "path": {"name": "/"},
        }
    )

    assert info["canScrollDescendants"] is False


def test_upload_forwards_relative_path() -> None:
    remote = _remote()
    remote._client.upload_file = Mock(
        return_value={"entry": {"id": "doc-1"}}
    )  # noqa: SLF001

    with TemporaryDirectory() as tmp:
        file_path = Path(tmp) / "doc.txt"
        file_path.write_text("hello", encoding="utf-8")
        remote.upload(file_path, parentId="parent-1", relative_path="sub/folder")

    remote._client.upload_file.assert_called_once_with(  # noqa: SLF001
        "parent-1",
        file_path,
        name=None,
        relative_path="sub/folder",
    )


def test_stream_file_forwards_relative_path() -> None:
    remote = _remote()
    remote._client.upload_file = Mock(  # noqa: SLF001
        return_value={
            "entry": {
                "id": "doc-1",
                "parentId": "parent-1",
                "name": "doc.txt",
                "isFolder": False,
                "path": {"name": "/Company Home/sub/folder"},
            }
        }
    )

    with TemporaryDirectory() as tmp:
        file_path = Path(tmp) / "doc.txt"
        file_path.write_text("hello", encoding="utf-8")
        remote.stream_file("parent-1", file_path, relativePath="sub/folder")

    remote._client.upload_file.assert_called_once_with(  # noqa: SLF001
        "parent-1",
        file_path,
        name=None,
        relative_path="sub/folder",
    )


def test_documents_get_accepts_path_keyword_for_root() -> None:
    remote = _remote()

    doc = remote.documents.get(path="/")

    assert doc.uid == "-root-"
    assert doc.path == "/"
    assert doc.type == "Folder"


def test_documents_get_resolves_path_via_client() -> None:
    remote = _remote()
    remote._client.get_node_by_path = Mock(  # noqa: SLF001
        return_value={
            "entry": {
                "id": "home-id",
                "name": "admin",
                "isFolder": True,
                "path": {"name": "/User Homes/admin"},
                "allowableOperations": ["read", "create", "update"],
            }
        }
    )

    doc = remote.documents.get(path="/User Homes/admin")

    remote._client.get_node_by_path.assert_called_once_with(
        "/User Homes/admin"
    )  # noqa: SLF001
    assert doc.uid == "home-id"
    assert doc.path == "/User Homes/admin"
    assert doc.type == "cm:folder"
    assert doc.contextParameters["permissions"] == ["Read", "AddChildren", "ReadWrite"]


def test_documents_get_returns_fallback_on_path_resolution_error() -> None:
    remote = _remote()
    remote._client.get_node_by_path = Mock(
        side_effect=RuntimeError("boom")
    )  # noqa: SLF001

    doc = remote.documents.get(path="/missing/path")

    assert doc.uid == ""
    assert doc.path == "/missing/path"
    assert doc.title == "path"


def test_documents_query_returns_only_folder_children() -> None:
    remote = _remote()
    remote._list_all_children_entries = Mock(  # noqa: SLF001
        return_value=[
            {
                "entry": {
                    "id": "folder-1",
                    "name": "Folder",
                    "isFolder": True,
                    "path": {"name": "/Company Home"},
                }
            },
            {
                "entry": {
                    "id": "file-1",
                    "name": "doc.txt",
                    "isFolder": False,
                    "path": {"name": "/Company Home"},
                }
            },
        ]
    )

    result = remote.documents.query(opts={"queryParams": "parent-1"})

    remote._list_all_children_entries.assert_called_once_with(
        "parent-1"
    )  # noqa: SLF001
    assert result["isNextPageAvailable"] is False
    assert [doc.uid for doc in result["entries"]] == ["folder-1"]


def test_alfresco_permissions_maps_allowable_operations() -> None:
    perms = _alfresco_permissions({"allowableOperations": ["read", "create", "update"]})

    assert perms == ["Read", "AddChildren", "ReadWrite"]


def test_alfresco_permissions_defaults_when_missing() -> None:
    perms = _alfresco_permissions({})

    assert perms == ["Read", "ReadWrite", "AddChildren"]


def test_personal_space_falls_back_to_my_node_when_path_lookup_404(caplog) -> None:
    remote = _remote()
    remote._client.get_node_by_path = Mock(  # noqa: SLF001
        side_effect=AlfrescoClientError("not found", status_code=404)
    )
    remote._client.get_node = Mock(  # noqa: SLF001
        return_value={
            "entry": {
                "id": "my-home-id",
                "path": {"name": "/User Homes/admin"},
                "allowableOperations": ["read", "create", "update"],
            }
        }
    )

    with caplog.at_level("DEBUG"):
        doc = remote.personal_space()

    assert doc.uid == "my-home-id"
    assert doc.path == "/User Homes/admin"
    remote._client.get_node.assert_called_once_with("-my-")  # noqa: SLF001
    records = [
        rec
        for rec in caplog.records
        if "falling back to '-my-' lookup" in rec.getMessage()
    ]
    assert records
    assert all(rec.exc_info is None for rec in records)


def test_get_doc_enricher_returns_list_for_gui() -> None:
    remote = _remote()

    doc_types = remote.get_doc_enricher("parent-1", "subtypes", False)
    folder_types = remote.get_doc_enricher("parent-1", "subtypes", True)

    assert isinstance(doc_types, list)
    assert isinstance(folder_types, list)
