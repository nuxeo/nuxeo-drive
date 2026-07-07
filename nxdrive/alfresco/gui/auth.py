"""Alfresco-specific GUI authentication flows."""


def basic_auth(api, local_folder: str, server_url: str, username: str, password: str):
    """Bind an Alfresco server using username/password."""
    api.bind_server(
        local_folder,
        server_url,
        username,
        password=password,
    )
