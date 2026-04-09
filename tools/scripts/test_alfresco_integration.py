#!/usr/bin/env python3
"""Quick integration test for Alfresco server connectivity and basic operations."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from nxdrive.client.alfresco import AlfrescoClient, AlfrescoClientError


def test_connectivity(url: str, username: str, password: str) -> None:
    """Test basic server connectivity and authentication."""
    print(f"🔗 Testing connectivity to {url}")
    client = AlfrescoClient(url, username=username, password=password, verify=False)

    try:
        token = client.authenticate()
        print("✅ Authentication successful")
        print(f"   Token: {token[:20]}..." if len(token) > 20 else f"   Token: {token}")
    except AlfrescoClientError as e:
        print(f"❌ Authentication failed: {e}")
        return


def test_list_root(url: str, username: str, password: str) -> None:
    """List root nodes."""
    print("\n📂 Listing root nodes")
    client = AlfrescoClient(url, username=username, password=password, verify=False)

    try:
        client.authenticate()
        payload = client.list_nodes("-root-")
        entries = payload.get("list", {}).get("entries", [])
        print(f"✅ Found {len(entries)} items in root")
        for entry in entries[:5]:
            node = entry.get("entry", {})
            name = node.get("name", "?")
            is_folder = "📁" if node.get("isFolder") else "📄"
            print(f"   {is_folder} {name}")
        if len(entries) > 5:
            print(f"   ... and {len(entries) - 5} more")
    except AlfrescoClientError as e:
        print(f"❌ Failed to list nodes: {e}")


def test_create_and_delete_folder(url: str, username: str, password: str) -> None:
    """Create a test folder and delete it."""
    print("\n🗂️  Testing folder creation/deletion")
    client = AlfrescoClient(url, username=username, password=password, verify=False)

    try:
        client.authenticate()

        # Create folder
        folder_name = "nxdrive-test-folder"
        print(f"   Creating folder: {folder_name}")
        result = client._request(  # noqa: SLF001
            "POST",
            f"{client.API_BASE}/nodes/-root-/children",
            json={"name": folder_name, "nodeType": "cm:folder"},
            expected_statuses=(200, 201),
        )
        folder_entry = result.get("entry", {})
        folder_id = folder_entry.get("id")

        if folder_id:
            print(f"✅ Folder created: {folder_id}")

            # Delete folder
            print(f"   Deleting folder: {folder_id}")
            client.delete_node(folder_id)
            print("✅ Folder deleted")
        else:
            print("❌ Failed to create folder (no ID in response)")
    except AlfrescoClientError as e:
        print(f"❌ Folder operation failed: {e}")


def test_upload_file(url: str, username: str, password: str) -> None:
    """Upload and delete a test file."""
    print("\n📤 Testing file upload/download")
    client = AlfrescoClient(url, username=username, password=password, verify=False)

    try:
        client.authenticate()

        # Create temporary test file
        with TemporaryDirectory() as tmp:
            test_file = Path(tmp) / "test.txt"
            test_file.write_text("Hello from Nuxeo Drive Alfresco integration test!")

            # Upload
            print(f"   Uploading: {test_file.name}")
            result = client.upload_file("-root-", test_file, name="nxdrive-test.txt")
            entry = result.get("entry", {})
            file_id = entry.get("id")

            if file_id:
                print(f"File uploaded: {file_id}")

                # Delete
                print(f"Deleting file: {file_id}")
                client.delete_node(file_id)
                print("file deleted")
            else:
                print("Failed to upload file (no ID in response)")
    except AlfrescoClientError as e:
        print(f"File operation failed: {e}")


def main() -> int:
    """Run all tests."""
    parser = argparse.ArgumentParser(
        description="Test Alfresco server connectivity and AlfrescoClient"
    )
    parser.add_argument(
        "--url", default="http://localhost:8080", help="Alfresco server URL"
    )
    parser.add_argument("--username", default="admin", help="Username")
    parser.add_argument("--password", default="admin", help="Password")
    parser.add_argument("--verify", action="store_true", help="Verify SSL certificates")
    args = parser.parse_args()

    print(" Alfresco Integration Test\n")
    print(f" Server: {args.url}")
    print(f" User: {args.username}")
    print(f" SSL verify: {args.verify}\n")

    try:
        test_connectivity(args.url, args.username, args.password)
        test_list_root(args.url, args.username, args.password)
        test_create_and_delete_folder(args.url, args.username, args.password)
        test_upload_file(args.url, args.username, args.password)

        print("\nAll tests completed!")
        return 0
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
