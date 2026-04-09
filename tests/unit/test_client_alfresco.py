from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock

import pytest

from nxdrive.client.alfresco.client import AlfrescoClient, AlfrescoClientError


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b"x"):
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content

    def json(self):
        return self._payload


def test_authenticate_stores_ticket() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(
        201,
        payload={"entry": {"id": "ticket_abc"}},
    )

    client = AlfrescoClient(
        "https://alfresco.local",
        username="alice",
        password="secret",
        session=session,
    )

    token = client.authenticate()

    assert token == "ticket_abc"
    assert client.token == "ticket_abc"


def test_list_nodes_uses_ticket_query_parameter() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(
        200,
        payload={"list": {"entries": []}},
    )

    client = AlfrescoClient(
        "https://alfresco.local", token="known_token", session=session
    )
    payload = client.list_nodes("-root-")

    assert "list" in payload
    request_args = session.request.call_args.kwargs
    assert request_args["params"]["alf_ticket"] == "known_token"


def test_upload_file_posts_multipart() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(
        201,
        payload={"entry": {"id": "new-id"}},
    )

    client = AlfrescoClient(
        "https://alfresco.local", token="known_token", session=session
    )

    with TemporaryDirectory() as tmp:
        file_path = Path(tmp) / "doc.txt"
        file_path.write_text("hello", encoding="utf-8")
        payload = client.upload_file("parent-1", file_path)

    assert payload["entry"]["id"] == "new-id"
    assert session.request.call_args.args[0] == "POST"


def test_upload_file_sends_normalized_relative_path() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(
        201,
        payload={"entry": {"id": "new-id"}},
    )

    client = AlfrescoClient(
        "https://alfresco.local", token="known_token", session=session
    )

    with TemporaryDirectory() as tmp:
        file_path = Path(tmp) / "doc.txt"
        file_path.write_text("hello", encoding="utf-8")
        client.upload_file("parent-1", file_path, relative_path="/a\\b/")

    assert session.request.call_args.kwargs["data"]["relativePath"] == "a/b"


def test_upload_file_omits_empty_relative_path() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(
        201,
        payload={"entry": {"id": "new-id"}},
    )

    client = AlfrescoClient(
        "https://alfresco.local", token="known_token", session=session
    )

    with TemporaryDirectory() as tmp:
        file_path = Path(tmp) / "doc.txt"
        file_path.write_text("hello", encoding="utf-8")
        client.upload_file("parent-1", file_path, relative_path="./")

    assert "relativePath" not in session.request.call_args.kwargs["data"]


def test_upload_file_omits_single_dot_relative_path() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(
        201,
        payload={"entry": {"id": "new-id"}},
    )

    client = AlfrescoClient(
        "https://alfresco.local", token="known_token", session=session
    )

    with TemporaryDirectory() as tmp:
        file_path = Path(tmp) / "doc.txt"
        file_path.write_text("hello", encoding="utf-8")
        client.upload_file("parent-1", file_path, relative_path=".")

    assert "relativePath" not in session.request.call_args.kwargs["data"]


def test_upload_file_strips_dot_slash_prefix_from_relative_path() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(
        201,
        payload={"entry": {"id": "new-id"}},
    )

    client = AlfrescoClient(
        "https://alfresco.local", token="known_token", session=session
    )

    with TemporaryDirectory() as tmp:
        file_path = Path(tmp) / "doc.txt"
        file_path.write_text("hello", encoding="utf-8")
        client.upload_file("parent-1", file_path, relative_path="./a/b")

    assert session.request.call_args.kwargs["data"]["relativePath"] == "a/b"


def test_get_node_by_path_strips_leading_slash_and_requests_permissions() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(
        200,
        payload={"entry": {"id": "user-home-id"}},
    )

    client = AlfrescoClient(
        "https://alfresco.local", token="known_token", session=session
    )

    payload = client.get_node_by_path("/User Homes/admin")

    assert payload["entry"]["id"] == "user-home-id"
    assert session.request.call_args.args == (
        "GET",
        "https://alfresco.local/alfresco/api/-default-/public/alfresco/versions/1/nodes/-root-",
    )
    assert session.request.call_args.kwargs["params"] == {
        "relativePath": "User Homes/admin",
        "include": "allowableOperations",
        "alf_ticket": "known_token",
    }


def test_get_node_by_path_retries_with_company_home_prefix_for_user_homes() -> None:
    session = Mock()
    session.request.side_effect = [
        FakeResponse(404, payload={"error": {"errorKey": "NotFound"}}),
        FakeResponse(200, payload={"entry": {"id": "user-home-id"}}),
    ]

    client = AlfrescoClient(
        "https://alfresco.local", token="known_token", session=session
    )

    payload = client.get_node_by_path("/User Homes/admin")

    assert payload["entry"]["id"] == "user-home-id"
    assert session.request.call_count == 2
    first_params = session.request.call_args_list[0].kwargs["params"]
    second_params = session.request.call_args_list[1].kwargs["params"]
    assert first_params["relativePath"] == "User Homes/admin"
    assert second_params["relativePath"] == "Company Home/User Homes/admin"


def test_delete_node_returns_none() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(204, payload={}, content=b"")
    client = AlfrescoClient(
        "https://alfresco.local", token="known_token", session=session
    )

    result = client.delete_node("node-1")

    assert result is None


def test_request_raises_on_unexpected_status() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(
        500,
        payload={"error": {"errorKey": "ServerError"}},
    )
    client = AlfrescoClient(
        "https://alfresco.local", token="known_token", session=session
    )

    with pytest.raises(AlfrescoClientError) as exc:
        client.get_node("node-1")

    assert exc.value.status_code == 500
    assert "Alfresco request failed" in str(exc.value)


def test_get_sync_service_configuration_uses_private_api_and_sync_base_url() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(
        200,
        payload={"entry": {"enabled": True}},
    )

    client = AlfrescoClient(
        "https://alfresco.local",
        sync_base_url="http://localhost:9090",
        token="known_token",
        session=session,
    )

    payload = client.get_sync_service_configuration()

    assert payload["entry"]["enabled"] is True
    assert session.request.call_args.args[1] == (
        "http://localhost:9090"
        "/alfresco/api/-default-/private/alfresco/versions/1/config/syncServiceConfiguration"
    )
    assert session.request.call_args.kwargs["params"]["alf_ticket"] == "known_token"


def test_start_subscription_sync_posts_private_api() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(
        202,
        payload={"entry": {"syncId": "sync-123"}},
    )

    client = AlfrescoClient(
        "https://alfresco.local",
        sync_base_url="http://localhost:9090",
        token="known_token",
        session=session,
    )

    payload = client.start_subscription_sync(
        "subscriber-a",
        "company-home",
        json={"since": 42},
    )

    assert payload["entry"]["syncId"] == "sync-123"
    assert session.request.call_args.args == (
        "POST",
        "http://localhost:9090"
        "/alfresco/api/-default-/private/alfresco/versions/1/"
        "subscribers/subscriber-a/subscriptions/company-home/sync",
    )
    assert session.request.call_args.kwargs["json"] == {"since": 42}


def test_create_subscription_posts_expected_payload() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(
        201,
        payload={"entry": {"id": "sub-1"}},
    )

    client = AlfrescoClient(
        "https://alfresco.local",
        sync_base_url="http://localhost:9090",
        token="known_token",
        session=session,
    )

    payload = client.create_subscription(
        "da6fa847-6dbf-4b17-8f8b-aefb2e311182",
        target_path="/Sites/site1/documentLibrary",
        subscription_type="BOTH",
    )

    assert payload["entry"]["id"] == "sub-1"
    assert session.request.call_args.args == (
        "POST",
        "http://localhost:9090"
        "/alfresco/api/-default-/private/alfresco/versions/1/"
        "subscribers/da6fa847-6dbf-4b17-8f8b-aefb2e311182/subscriptions",
    )
    assert session.request.call_args.kwargs["json"] == {
        "targetPath": "/Sites/site1/documentLibrary",
        "subscriptionType": "BOTH",
    }


def test_create_subscription_raises_on_rejected_payload() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(
        400,
        payload={"error": {"errorKey": "InvalidSubscription"}},
    )

    client = AlfrescoClient(
        "https://alfresco.local",
        sync_base_url="http://localhost:9090",
        token="known_token",
        session=session,
    )

    with pytest.raises(AlfrescoClientError) as exc:
        client.create_subscription(
            "da6fa847-6dbf-4b17-8f8b-aefb2e311182",
            target_path="",
            subscription_type="BOTH",
        )

    assert exc.value.status_code == 400


def test_cancel_subscription_sync_returns_none() -> None:
    session = Mock()
    session.request.return_value = FakeResponse(204, payload={}, content=b"")

    client = AlfrescoClient(
        "https://alfresco.local",
        sync_base_url="http://localhost:9090",
        token="known_token",
        session=session,
    )

    result = client.cancel_subscription_sync("subscriber-a", "company-home", "sync-123")

    assert result is None
    assert session.request.call_args.args == (
        "DELETE",
        "http://localhost:9090"
        "/alfresco/api/-default-/private/alfresco/versions/1/"
        "subscribers/subscriber-a/subscriptions/company-home/sync/sync-123",
    )


def test_sync_service_uses_environment_override(monkeypatch) -> None:
    session = Mock()
    session.request.return_value = FakeResponse(
        200,
        payload={"entry": {"url": "ok"}},
    )
    monkeypatch.setenv("ALFRESCO_SYNC_URL", "http://localhost:9090")

    client = AlfrescoClient(
        "https://alfresco.local",
        token="known_token",
        session=session,
    )

    client.get_sync_service()

    assert session.request.call_args.args == (
        "GET",
        "http://localhost:9090"
        "/alfresco/api/-default-/private/alfresco/versions/1/config/syncService",
    )
