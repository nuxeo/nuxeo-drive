"""Unit tests for nxdrive.nuxeo.objects — additional coverage for from_dict and get_blob."""

import pytest

from nxdrive.drive.exceptions import DriveError
from nxdrive.nuxeo.objects import NuxeoDocumentInfo


def _make_doc(**overrides):
    """Create a minimal valid document dict."""
    props = overrides.pop("properties", {"dc:title": "Doc"})
    if "dc:title" not in props:
        props["dc:title"] = "Doc"
    doc = {
        "uid": "uid-1",
        "path": "/ws/Doc",
        "root": "root-1",
        "properties": props,
        "facets": overrides.pop("facets", ["Versionable"]),
        "lastModified": "2025-06-01T12:00:00Z",
        "type": overrides.pop("type", "File"),
    }
    doc.update(overrides)
    return doc


class TestFromDictEdgeCases:
    def test_none_doc_raises(self):
        with pytest.raises(DriveError):
            NuxeoDocumentInfo.from_dict(None)

    def test_missing_properties_raises(self):
        with pytest.raises(DriveError):
            NuxeoDocumentInfo.from_dict({"uid": "x", "root": "r", "path": "/p"})

    def test_lock_created_none(self):
        doc = _make_doc(lockOwner="admin", lockCreated=None)
        info = NuxeoDocumentInfo.from_dict(doc)
        assert info.lock_owner == "admin"
        assert info.lock_created is None

    def test_state_field(self):
        doc = _make_doc(state="approved")
        info = NuxeoDocumentInfo.from_dict(doc)
        assert info.state == "approved"

    def test_doc_type_from_type_field(self):
        doc = _make_doc(type="Note")
        info = NuxeoDocumentInfo.from_dict(doc)
        assert info.doc_type == "Note"


class TestGetBlobNote:
    def test_note_with_content(self):
        props = {
            "dc:title": "MyNote",
            "note:note": "Hello World",
            "note:mime_type": "text/plain",
        }
        doc = _make_doc(properties=props, type="Note")
        info = NuxeoDocumentInfo.from_dict(doc)
        blob = info.get_blob("note:note")
        assert blob is not None
        assert blob.name == "MyNote"
        # Digest should be computed from content
        assert blob.digest is not None
        assert blob.size == len("Hello World")

    def test_note_non_note_doctype_raises_on_string_blob(self):
        """When doc_type is NOT Note, note:note xpath uses standard path lookup.
        The value is a string which causes TypeError in Blob.from_dict."""
        props = {
            "dc:title": "RegularDoc",
            "note:note": "Some data",
        }
        doc = _make_doc(properties=props, type="File")
        info = NuxeoDocumentInfo.from_dict(doc)
        # Standard lookup returns the string "Some data", then Blob.from_dict
        # tries to index it with string keys which raises TypeError.
        with pytest.raises(TypeError):
            info.get_blob("note:note")


class TestGetBlobXpath:
    def test_deep_nested_path(self):
        props = {
            "dc:title": "DeepDoc",
            "custom:attachments": [
                [
                    {
                        "name": "deep.pdf",
                        "digest": "abc",
                        "digestAlgorithm": "md5",
                        "length": 100,
                        "mime-type": "application/pdf",
                        "data": "nxfile/deep.pdf",
                    }
                ]
            ],
        }
        doc = _make_doc(properties=props)
        info = NuxeoDocumentInfo.from_dict(doc)
        blob = info.get_blob("custom:attachments/0/0")
        assert blob is not None
        assert blob.name == "deep.pdf"

    def test_index_out_of_range_returns_none(self):
        props = {
            "dc:title": "Doc",
            "files:files": [{"file": {"name": "a.txt"}}],
        }
        doc = _make_doc(properties=props)
        info = NuxeoDocumentInfo.from_dict(doc)
        blob = info.get_blob("files:files/5/file")
        assert blob is None

    def test_key_error_returns_none(self):
        props = {
            "dc:title": "Doc",
            "files:files": [{"other_key": "value"}],
        }
        doc = _make_doc(properties=props)
        info = NuxeoDocumentInfo.from_dict(doc)
        blob = info.get_blob("files:files/0/file")
        assert blob is None
