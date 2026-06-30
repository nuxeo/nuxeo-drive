"""Nuxeo-specific protocol URL helpers."""

import re
from urllib.parse import unquote, urlparse


TOKEN_PATTERN = r"[^/]+"


def normalize_protocol_url(value: str) -> str:
    """Normalize browser callback variants to the canonical nxdrive:// form."""
    if value.startswith("nxdrive:") and not value.startswith("nxdrive://"):
        return f"nxdrive://{value[len('nxdrive:'):].lstrip('/')}"
    return value


def parse_direct_transfer_remote_path(value: str) -> str:
    """Extract Nuxeo remote path from a direct-transfer payload."""
    decoded = unquote(value.strip())
    parts = re.split("/nuxeo", decoded, maxsplit=1)
    if len(parts) < 2:
        raise ValueError("Missing /nuxeo in URL")
    return parts[1]


def normalize_download_server_path(server_part: str) -> str:
    """Normalize server path for Nuxeo direct-download links."""
    normalized = server_part.rstrip("/")
    parsed = urlparse(f"https://{normalized}")
    path = parsed.path.rstrip("/")
    if not path.endswith("/nuxeo"):
        normalized = f"{normalized}/nuxeo"
    return normalized
