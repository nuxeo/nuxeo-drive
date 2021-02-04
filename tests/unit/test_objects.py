from datetime import datetime
from typing import Any, Dict

import pytest

from nxdrive.exceptions import DriveError
from nxdrive.objects import Blob, NuxeoDocumentInfo, RemoteFileInfo


@pytest.fixture(scope="session")
def doc() -> NuxeoDocumentInfo:
    """Mega object with several blob xpaths."""
    return NuxeoDocumentInfo.from_dict(
        {
            "root": "root",
            "uid": "uid",
            "path": "path",
            "properties": {
                "dc:title": "dc:title",
                "blobholder:0": {
                    "name": "blob.empty",
                    "digest": "",
                    "digestAlgorithm": "sha256",
                    "length": 0,
                    "mime-type": "text/plain",
                    "data": "",
                },
                "blobholder:1": {
                    "name": "blob.empty",
                    "digest": "",
                    "digestAlgorithm": "sha256",
                    "length": 0,
                    "mime-type": "text/plain",
                    "data": "",
                },
                "file:content": {
                    "name": "file.empty",
                    "digest": "",
                    "digestAlgorithm": "sha256",
                    "length": 0,
                    "mime-type": "text/plain",
                    "data": "",
                },
                "files:files": [
                    {
                        "file": {
                            "name": "file.empty",
                            "digest": "",
                            "digestAlgorithm": "sha256",
                            "length": 0,
                            "mime-type": "text/plain",
                            "data": "",
                        }
                    }
                ],
                "foo:bar": [
                    {
                        "name": "file.empty",
                        "digest": "",
                        "digestAlgorithm": "sha256",
                        "length": 0,
                        "mime-type": "text/plain",
                        "data": "",
                    },
                    {
                        "name": "custom-multi-1",
                        "digest": "",
                        "digestAlgorithm": "sha256",
                        "length": 0,
                        "mime-type": "text/plain",
                        "data": "",
                    },
                ],
                "foo:baz": [
                    [
                        [
                            {
                                "real:file": {
                                    "name": "file.empty",
                                    "digest": "",
                                    "digestAlgorithm": "sha256",
                                    "length": 0,
                                    "mime-type": "text/plain",
                                    "data": "",
                                }
                            }
                        ]
                    ]
                ],
                "note:note": {
                    "name": "note.empty",
                    "digest": "",
                    "digestAlgorithm": "sha256",
                    "length": 0,
                    "mime-type": "text/plain",
                    "data": "",
                },
            },
            "facets": [],
            "lastModified": "2020-02-03 18:34:35",
        }
    )


@pytest.fixture(scope="function")
def remote_doc_dict() -> Dict[str, Any]:
    now = datetime.now()
    return {
        "id": "fake_id",
        "parentId": "fake_id",
        "path": "fake/path",
        "name": "Testing",
        "lastModificationDate": "string",
        "creationDate": now,
        "lockInfo": {"owner": "jdoe", "created": datetime.timestamp(now)},
    }


@pytest.mark.parametrize(
    "xpath",
    [
        "blobholder:0",
        "blobholder:1",
        "file:content",
        "files:files/0/file",
        "foo:bar/0",
        "foo:bar/1",
        "foo:baz/0/0/0/real:file",
        "note:note",
    ],
)
def test_get_blob_xpath(xpath, doc):
    """NXDRIVE-2027: Check (Direct Edit) works on all kind of custom blob metadata values."""
    assert isinstance(doc.get_blob(xpath), Blob)


@pytest.mark.parametrize(
    "xpath",
    [
        "blobholder:2",
        "file:contents",
        "files:files/1/file",
        "foo:bar/2",
        "foo:baz/1/0/0/real:file",
        "note:note/0",
        "unknown",
    ],
)
def test_get_blob_xpath_bad(xpath, doc):
    """Ensure that invalid xpath will not throw an error but simply return None."""
    assert doc.get_blob(xpath) is None


def test_remote_doc_folder(remote_doc_dict):
    remote_doc_dict["folder"] = True
    document = RemoteFileInfo.from_dict(remote_doc_dict)
    assert document.folderish


def test_remote_doc_digest(remote_doc_dict):
    remote_doc_dict["digestAlgorithm"] = "MD5"
    remote_doc_dict["digest"] = "fakedigest"
    document = RemoteFileInfo.from_dict(remote_doc_dict)
    assert document.digest == "fakedigest"
    assert document.digest_algorithm == "md5"


def test_remote_doc_async_digest(remote_doc_dict):
    remote_doc_dict["digest"] = "0123456789-0"
    remote_doc_dict["digestAlgorithm"] = None
    document = RemoteFileInfo.from_dict(remote_doc_dict)
    assert document.digest == "0123456789-0"
    assert not document.digest_algorithm


def test_remote_doc_live_connect_exotic_digest(remote_doc_dict):
    remote_doc_dict["digest"] = '"MTYxMTIyODA1ODUzNA"'
    remote_doc_dict["digestAlgorithm"] = None
    document = RemoteFileInfo.from_dict(remote_doc_dict)
    assert document.digest == '"MTYxMTIyODA1ODUzNA"'
    assert not document.digest_algorithm


def test_remote_doc_live_connect_standard_digest(remote_doc_dict):
    remote_doc_dict["digest"] = "0" * 64
    remote_doc_dict["digestAlgorithm"] = None
    document = RemoteFileInfo.from_dict(remote_doc_dict)
    assert document.digest == "0" * 64
    assert document.digest_algorithm == "sha256"


def test_remote_doc_raise_drive_error(remote_doc_dict):
    del remote_doc_dict["id"]
    with pytest.raises(DriveError):
        RemoteFileInfo.from_dict(remote_doc_dict)
