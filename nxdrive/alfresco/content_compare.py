"""
Content comparison for Alfresco pairs that have no metadata baseline.

A pair that has never synchronised carries no version label and no
``last_remote_updated`` worth comparing — both were written from the very
fetch that created it. Metadata therefore cannot answer "do these two sides
hold the same bytes?", and the only honest answer comes from the content
itself.

Hashing a whole file over the network is too expensive, so the comparison is
size first, then an MD5 over the first and last :data:`PARTIAL_COMPARE_SIZE`
bytes. Files up to twice that size are compared in full.
"""

import hashlib
from logging import getLogger
from pathlib import Path
from time import sleep
from typing import Any, Optional, Tuple

__all__ = (
    "PARTIAL_COMPARE_ATTEMPTS",
    "PARTIAL_COMPARE_SIZE",
    "content_matches",
    "local_head_tail_digest",
    "remote_head_tail_digest",
)

log = getLogger(__name__)

#: Bytes hashed from the head *and* from the tail. Files up to twice this
#: size are compared in full.
PARTIAL_COMPARE_SIZE = 10 * 1024 * 1024

#: Attempts allowed when reading remote content for the comparison.
PARTIAL_COMPARE_ATTEMPTS = 3


def local_head_tail_digest(path: Path, size: int, /, *, head_only: bool = False) -> str:
    limit = PARTIAL_COMPARE_SIZE
    h = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as f:
        if head_only:
            h.update(f.read(limit))
        elif size <= 2 * limit:
            for chunk in iter(lambda: f.read(limit), b""):
                h.update(chunk)
        else:
            h.update(f.read(limit))
            f.seek(size - limit)
            h.update(f.read(limit))
    return h.hexdigest()


def remote_head_tail_digest(
    remote: Any, node_id: str, size: int, /
) -> Tuple[str, bool]:
    """Return the digest and whether only the head window was hashed.

    A server ignoring ``Range`` cannot serve the tail cheaply, so the
    comparison degrades to head-only; the caller must then hash the local side
    the same way or every large file would look different.
    """
    limit = PARTIAL_COMPARE_SIZE
    h = hashlib.md5(usedforsecurity=False)
    if size <= 2 * limit:
        h.update(remote.get_content_range(node_id, 0, size) or b"")
        return h.hexdigest(), False

    h.update(remote.get_content_range(node_id, 0, limit) or b"")
    tail = remote.get_content_range(node_id, size - limit, limit)
    if tail is None:
        return h.hexdigest(), True
    h.update(tail)
    return h.hexdigest(), False


def content_matches(
    remote: Any,
    local_path: Path,
    node_id: str,
    /,
    *,
    remote_size: int = -1,
) -> Optional[bool]:
    """Return whether *local_path* and *node_id* hold the same content.

    ``None`` means the question could not be answered (unreadable file, server
    error); callers must not read that as "different".

    *remote_size* is fetched when not supplied, which costs one extra call.
    """
    try:
        local_size = local_path.stat().st_size
    except OSError:
        log.warning(f"Could not stat {str(local_path)!r}", exc_info=True)
        return None

    if remote_size < 0:
        try:
            node = remote.get_node(node_id)
        except Exception:
            log.warning(f"Could not read the size of {node_id!r}", exc_info=True)
            return None
        remote_size = node.content.size_in_bytes if node.content else -1

    if remote_size != local_size:
        log.info(
            f"{str(local_path)!r} differs in size from {node_id!r} "
            f"(remote={remote_size}, local={local_size})"
        )
        return False

    remote_digest = ""
    head_only = False
    for attempt in range(1, PARTIAL_COMPARE_ATTEMPTS + 1):
        try:
            remote_digest, head_only = remote_head_tail_digest(
                remote, node_id, remote_size
            )
            break
        except Exception:
            if attempt == PARTIAL_COMPARE_ATTEMPTS:
                log.warning(
                    f"Could not read the remote content of {node_id!r} after "
                    f"{attempt} attempts",
                    exc_info=True,
                )
                return None
            sleep(1)

    if head_only:
        log.info(
            f"Comparing only the first {PARTIAL_COMPARE_SIZE} bytes of "
            f"{node_id!r}: the server does not honour Range"
        )

    local_digest = local_head_tail_digest(local_path, local_size, head_only=head_only)
    if local_digest == remote_digest:
        return True

    log.info(
        f"{str(local_path)!r} differs in content from {node_id!r} "
        f"(remote={remote_digest}, local={local_digest})"
    )
    return False
