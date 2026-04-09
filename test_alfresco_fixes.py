#!/usr/bin/env python
"""
Quick smoke test to verify the Alfresco integration fixes are working.
This tests the key methods that were modified.
"""

from nuxeo.models import Document

from nxdrive.exceptions import NotFound


def test_alfresco_remote_stubs():
    """Test that stub methods exist and don't crash."""

    # Mock the AlfrescoClient
    class MockAlfrescoClient:
        API_BASE = "/test"

        def _request(self, *args, **kwargs):
            return {"entry": {}}

    # Create a minimal AlfrescoRemote instance
    from nxdrive.client.alfresco_remote import AlfrescoRemote

    remote = AlfrescoRemote(
        url="http://test", user_id="admin", device_id="test", version="1.0"
    )
    remote._client = MockAlfrescoClient()

    # Test 1: documents property exists and returns a stub
    assert hasattr(remote, "documents"), "documents property missing"
    docs = remote.documents
    assert docs is not None, "documents property returned None"
    print("✓ documents property works")

    # Test 2: documents.get() works for root
    root_doc = docs.get(path="/")
    assert isinstance(root_doc, Document), "documents.get() didn't return Document"
    assert root_doc.title == "Company Home", "Root document title wrong"
    print("✓ documents.get('/') works")

    # Test 3: personal_space() returns a Document
    personal = remote.personal_space()
    assert isinstance(personal, Document), "personal_space() didn't return Document"
    assert (
        "User Homes" in personal.path
    ), "personal_space path doesn't contain User Homes"
    print("✓ personal_space() works")

    # Test 4: NotFound is raised for missing nodes (not ValueError)
    try:
        # This will call get_fs_item which returns None, then get_fs_info raises NotFound
        remote.get_fs_info("missing-node-id")
        assert False, "Should have raised NotFound"
    except NotFound:
        print("✓ get_fs_info() raises NotFound for missing nodes")
    except Exception as e:
        assert False, f"get_fs_info() raised wrong exception: {type(e).__name__}"

    print("\nAll smoke tests passed! ✓")


if __name__ == "__main__":
    test_alfresco_remote_stubs()
