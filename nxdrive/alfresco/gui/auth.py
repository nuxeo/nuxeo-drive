"""Alfresco-specific GUI authentication flows."""

from typing import Any


def basic_auth(
    api: "Any", local_folder: str, server_url: str, username: str, password: str
) -> None:
    """Bind an Alfresco server using username/password."""
    api.bind_server(
        local_folder,
        server_url,
        username,
        password=password,
    )
