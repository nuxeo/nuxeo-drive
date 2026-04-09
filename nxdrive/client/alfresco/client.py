from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import requests


class AlfrescoClientError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class AlfrescoClient:
    """Small Alfresco REST client for incremental migration from Nuxeo-specific code."""

    API_BASE = "/alfresco/api/-default-/public/alfresco/versions/1"
    AUTH_BASE = "/alfresco/api/-default-/public/authentication/versions/1"
    PRIVATE_API_BASE = "/alfresco/api/-default-/private/alfresco/versions/1"

    def __init__(
        self,
        base_url: str,
        /,
        *,
        username: str = "",
        password: str = "",
        token: str = "",
        verify: bool = True,
        timeout: int = 30,
        sync_base_url: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        resolved_sync_base_url = sync_base_url or os.getenv("ALFRESCO_SYNC_URL", "")
        self.sync_base_url = (
            resolved_sync_base_url.rstrip("/")
            if resolved_sync_base_url
            else self.base_url
        )
        self.username = username
        self.password = password
        self.token = token
        self.verify = verify
        self.timeout = timeout
        self._session = session or requests.Session()

    def authenticate(self) -> str:
        """Request an Alfresco ticket and store it as a bearer token."""
        if self.token:
            return self.token

        if not self.username or not self.password:
            raise AlfrescoClientError(
                "username and password are required to authenticate"
            )

        payload = {"userId": self.username, "password": self.password}
        data = self._request(
            "POST",
            f"{self.AUTH_BASE}/tickets",
            json=payload,
            expected_statuses=(200, 201),
            auth_required=False,
        )

        entry = data.get("entry", {})
        ticket = entry.get("id")
        if not ticket:
            raise AlfrescoClientError(
                "authentication response did not include a ticket", payload=data
            )

        self.token = ticket
        return self.token

    def list_nodes(
        self,
        parent_id: str = "-root-",
        /,
        *,
        max_items: int = 100,
        skip_count: int = 0,
    ) -> Dict[str, Any]:
        params = {
            "maxItems": max_items,
            "skipCount": skip_count,
            "include": "allowableOperations",
        }
        return self._request(
            "GET",
            f"{self.API_BASE}/nodes/{parent_id}/children",
            params=params,
        )

    def get_node(self, node_id: str, /) -> Dict[str, Any]:
        return self._request(
            "GET",
            f"{self.API_BASE}/nodes/{node_id}",
            params={"include": "allowableOperations"},
        )

    def get_node_by_path(self, path: str, /) -> Dict[str, Any]:
        """Resolve an Alfresco repository path to a node entry.

        Alfresco supports resolving a path relative to the repository root via
        the ``relativePath`` query parameter on any ``/nodes/{id}`` endpoint.
        Leading slashes are stripped automatically.
        """
        relative_path = path.lstrip("/")
        candidate_paths = [relative_path]
        # Some ACS deployments expose the root path with an explicit
        # "Company Home" segment for relative path resolution.
        if relative_path.startswith("User Homes/"):
            candidate_paths.append(f"Company Home/{relative_path}")

        last_error: Optional[AlfrescoClientError] = None
        for candidate in candidate_paths:
            try:
                return self._request(
                    "GET",
                    f"{self.API_BASE}/nodes/-root-",
                    params={
                        "relativePath": candidate,
                        "include": "allowableOperations",
                    },
                )
            except AlfrescoClientError as exc:
                last_error = exc
                if exc.status_code != 404:
                    raise
        if last_error is not None:
            raise last_error
        raise AlfrescoClientError("Unable to resolve node by path")

    def upload_file(
        self,
        parent_id: str,
        file_path: Path,
        /,
        *,
        name: str = "",
        auto_rename: bool = True,
        relative_path: str = "",
    ) -> Dict[str, Any]:
        upload_name = name or file_path.name
        data = {
            "name": upload_name,
            "autoRename": str(auto_rename).lower(),
        }
        normalized_relative_path = _normalize_relative_path(relative_path)
        if normalized_relative_path:
            data["relativePath"] = normalized_relative_path

        with file_path.open("rb") as stream:
            files = {
                "filedata": (upload_name, stream, "application/octet-stream"),
            }
            return self._request(
                "POST",
                f"{self.API_BASE}/nodes/{parent_id}/children",
                data=data,
                files=files,
                expected_statuses=(200, 201),
            )

    def delete_node(self, node_id: str, /, *, permanent: bool = False) -> None:
        params = {"permanent": str(permanent).lower()}
        self._request(
            "DELETE",
            f"{self.API_BASE}/nodes/{node_id}",
            params=params,
            expected_statuses=(200, 202, 204),
        )

    def get_subscription(
        self, subscriber_id: str, subscription_id: str, /
    ) -> Dict[str, Any]:
        return self._request(
            "GET",
            f"{self.PRIVATE_API_BASE}/subscribers/{subscriber_id}/subscriptions/{subscription_id}",
            base_url=self.sync_base_url,
        )

    def create_subscription(
        self,
        subscriber_id: str,
        /,
        *,
        target_path: str,
        subscription_type: str = "BOTH",
    ) -> Dict[str, Any]:
        payload = {
            "targetPath": target_path,
            "subscriptionType": subscription_type,
        }
        return self._request(
            "POST",
            f"{self.PRIVATE_API_BASE}/subscribers/{subscriber_id}/subscriptions",
            json=payload,
            expected_statuses=(200, 201),
            base_url=self.sync_base_url,
        )

    def start_subscription_sync(
        self,
        subscriber_id: str,
        subscriptions_query: str,
        /,
        *,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._request(
            "POST",
            f"{self.PRIVATE_API_BASE}/subscribers/{subscriber_id}/subscriptions/{subscriptions_query}/sync",
            json=json or {},
            expected_statuses=(200, 201, 202),
            base_url=self.sync_base_url,
        )

    def get_subscription_sync(
        self,
        subscriber_id: str,
        subscriptions_query: str,
        sync_id: str,
        /,
    ) -> Dict[str, Any]:
        return self._request(
            "GET",
            f"{self.PRIVATE_API_BASE}/subscribers/{subscriber_id}/subscriptions/{subscriptions_query}/sync/{sync_id}",
            base_url=self.sync_base_url,
        )

    def cancel_subscription_sync(
        self,
        subscriber_id: str,
        subscriptions_query: str,
        sync_id: str,
        /,
    ) -> None:
        self._request(
            "DELETE",
            f"{self.PRIVATE_API_BASE}/subscribers/{subscriber_id}/subscriptions/{subscriptions_query}/sync/{sync_id}",
            expected_statuses=(200, 202, 204),
            base_url=self.sync_base_url,
        )

    def get_sync_service(self) -> Dict[str, Any]:
        return self._request(
            "GET",
            f"{self.PRIVATE_API_BASE}/config/syncService",
            base_url=self.sync_base_url,
        )

    def get_sync_service_configuration(self) -> Dict[str, Any]:
        return self._request(
            "GET",
            f"{self.PRIVATE_API_BASE}/config/syncServiceConfiguration",
            base_url=self.sync_base_url,
        )

    def _request(
        self,
        method: str,
        path: str,
        /,
        *,
        expected_statuses: Iterable[int] = (200,),
        auth_required: bool = True,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if auth_required and not self.token:
            self.authenticate()

        headers = dict(kwargs.pop("headers", {}) or {})
        params = dict(kwargs.pop("params", {}) or {})
        base_url = str(kwargs.pop("base_url", self.base_url)).rstrip("/")

        url = f"{base_url}{path}"

        def send_request(ticket: str = "", *, basic: bool = False) -> requests.Response:
            req_params = dict(params)
            if ticket:
                # Alfresco ticket auth uses query parameter.
                req_params["alf_ticket"] = ticket
            auth = (self.username, self.password) if basic else None
            return self._session.request(
                method,
                url,
                headers=headers,
                params=req_params,
                auth=auth,
                verify=self.verify,
                timeout=self.timeout,
                **kwargs,
            )

        use_basic = bool(self.username and self.password)
        resp = send_request(self.token, basic=use_basic)

        # Tickets can expire quickly; refresh once transparently.
        if (
            auth_required
            and resp.status_code == requests.codes.unauthorized
            and self.username
            and self.password
        ):
            self.token = ""
            self.authenticate()
            resp = send_request(self.token, basic=True)
            if resp.status_code == requests.codes.unauthorized:
                # Last-resort fallback for deployments not honoring `alf_ticket`
                # consistently on all endpoints.
                resp = send_request(basic=True)

        if resp.status_code not in tuple(expected_statuses):
            raise AlfrescoClientError(
                f"Alfresco request failed: {resp.status_code} {method} {path}",
                status_code=resp.status_code,
                payload=_safe_json(resp),
            )

        # 204/empty responses are valid for some operations like DELETE.
        if not getattr(resp, "content", b""):
            return {}
        return _safe_json(resp)


def _safe_json(response: requests.Response) -> Dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {"value": data}


def _normalize_relative_path(relative_path: str, /) -> str:
    # 1. Replace backslashes, strip surrounding whitespace
    normalized = str(relative_path or "").replace("\\", "/").strip()
    # 2. Strip leading/trailing slashes
    normalized = normalized.strip("/")
    # 3. Collapse leading "./" segments (e.g. "./" or "./foo" → "foo")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    # 4. A bare "." means current dir → empty
    if normalized == ".":
        return ""
    return normalized
