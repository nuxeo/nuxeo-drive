"""Alfresco-specific GUI authentication flows."""

from nxdrive.drive.utils import get_verify, normalized_path


def basic_auth(api, local_folder: str, server_url: str, username: str, password: str):
    """Bind an Alfresco server using username/password."""
    api.bind_server(
        local_folder,
        server_url,
        username,
        password=password,
    )


def oauth2_password_auth(
    api,
    local_folder: str,
    server_url: str,
    username: str,
    password: str,
):
    """Bind an Alfresco server using OAuth2 Resource Owner Password Grant."""
    from nxdrive.drive.server_type import detect_by_url, load_class

    if not api._manager.check_local_folder_available(normalized_path(local_folder)):
        api.setMessage.emit("FOLDER_USED", "error")
        return

    detected = detect_by_url(server_url)
    oauth2_cls = load_class(detected.oauth2_class_path)
    if not oauth2_cls or not hasattr(oauth2_cls, "password_grant"):
        api.setMessage.emit("CONNECTION_REFUSED", "error")
        return

    try:
        result = oauth2_cls.password_grant(
            server_url,
            username,
            password,
            verify=get_verify(),
        )
    except Exception:
        api.setMessage.emit("CONNECTION_REFUSED", "error")
        return

    token = {
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token"),
        "token_url": result.get("token_url"),
        "client_id": result.get("client_id"),
    }
    resolved_username = result.get("username", username)

    api.bind_server(
        local_folder,
        server_url,
        resolved_username,
        token=token,
    )
