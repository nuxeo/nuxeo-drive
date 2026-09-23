#!/usr/bin/env python3
"""Live capture harness for the Alfresco Enterprise Sync Service (dsync) delta feed.

Phase 0 spike tool. Provisions a device subscriber + node subscription against a live
ACS Enterprise + service-sync stack, drives the full change matrix (create / edit /
rename / create-folder / move / delete-file / delete-folder), pulls the resulting deltas
via the async start/poll/clear protocol, asserts the ``seqNo`` marker is monotonic, writes
one fixture per event, and cleans up everything it created.

Requires ``alfresco-rest-client>=1.0.2``. Run against a throwaway/dev server only.

    python capture_deltas.py

Environment overrides: ALF_REPO, ALF_SYNC, ALF_USER, ALF_PASS, ALF_CLIENT_VERSION.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import requests
from alfresco import Alfresco

REPO = os.environ.get("ALF_REPO", "http://localhost:8080/alfresco")
SYNC = os.environ.get("ALF_SYNC", "http://localhost:9090/alfresco")
USER = os.environ.get("ALF_USER", "admin")
PASS = os.environ.get("ALF_PASS", "admin")
CLIENT_VERSION = os.environ.get("ALF_CLIENT_VERSION", "1.0.1")

FIXTURES = Path(__file__).with_name("fixtures")
PRIV = f"{REPO}/api/-default-/private/alfresco/versions/1"
CORE = f"{REPO}/api/-default-/public/alfresco/versions/1"

SETTLE = 1.5  # seconds to let a change propagate repo -> event2 -> sync service
DRAIN_ROUNDS = 6  # times to re-poll before declaring an event drained


def _sess() -> requests.Session:
    s = requests.Session()
    s.auth = (USER, PASS)
    s.headers["Content-Type"] = "application/json"
    return s


def provision(s: requests.Session, folder_id: str) -> tuple[str, str]:
    """Register a device subscriber and a BOTH subscription on ``folder_id``."""
    r = s.post(
        f"{PRIV}/subscribers",
        data=json.dumps({"deviceOS": "darwin", "clientVersion": CLIENT_VERSION}),
    )
    r.raise_for_status()
    subscriber = r.json()["entry"]["id"]

    r = s.post(
        f"{PRIV}/subscribers/{subscriber}/subscriptions",
        data=json.dumps({"targetNodeId": folder_id, "subscriptionType": "BOTH"}),
    )
    r.raise_for_status()
    subscription = r.json()["entry"]["id"]
    return subscriber, subscription


def deprovision(s: requests.Session, subscriber: str) -> None:
    s.delete(f"{PRIV}/subscribers/{subscriber}")


def pull(client: Alfresco, subscriber: str, subscription: str) -> list[dict]:
    """Drain all currently available changes, acknowledging each batch.

    Returns the flattened list of change dicts (from ``SyncStatus._raw``)."""
    collected: list[dict] = []
    for _ in range(DRAIN_ROUNDS):
        started = client.sync_service.start_sync(
            subscriber, subscription, {"clientVersion": CLIENT_VERSION, "changes": []}
        )
        sync_id = started.sync_id
        for _ in range(20):
            status = client.sync_service.get_sync(subscriber, subscription, sync_id)
            if status.status in ("ready", "error"):
                break
            time.sleep(0.25)
        raw = getattr(status, "_raw", {}) or {}
        changes = raw.get("changes", []) or []
        collected.extend(changes)
        client.sync_service.clear_sync(subscriber, subscription, sync_id)
        if not raw.get("moreChanges"):
            break
        time.sleep(0.2)
    return collected


def _mkfolder(s: requests.Session, parent: str, name: str) -> str:
    r = s.post(
        f"{CORE}/nodes/{parent}/children",
        data=json.dumps({"name": name, "nodeType": "cm:folder"}),
    )
    r.raise_for_status()
    return r.json()["entry"]["id"]


def _mkfile(
    s: requests.Session, parent: str, name: str, content: bytes = b"hello"
) -> str:
    r = s.post(
        f"{CORE}/nodes/{parent}/children",
        data=json.dumps({"name": name, "nodeType": "cm:content"}),
    )
    r.raise_for_status()
    node = r.json()["entry"]["id"]
    s.put(
        f"{CORE}/nodes/{node}/content",
        data=content,
        headers={"Content-Type": "text/plain"},
    )
    return node


def main() -> None:
    FIXTURES.mkdir(exist_ok=True)
    s = _sess()
    # The vendor ``alfresco`` client prepends ``/alfresco/api/…`` internally, so
    # it must be given the bare origin. Passing ``REPO`` (which ends in
    # ``/alfresco``) would make it target a doubled ``/alfresco/alfresco/…``
    # path and fail to connect. Keep ``REPO`` for the raw PRIV/CORE URLs above.
    client_url = REPO[: -len("/alfresco")] if REPO.endswith("/alfresco") else REPO
    client = Alfresco(url=client_url, auth=(USER, PASS), sync_service_url=SYNC)

    tag = uuid.uuid4().hex[:6]
    root = _mkfolder(s, "-root-", f"dsync-cap-{tag}")

    subscriber, subscription = provision(s, root)
    # give the subscription time to register in the sync service before first pull
    time.sleep(3)

    summary: list[dict] = []
    max_seq = 0
    file_id: str | None = None
    subfolder_id: str | None = None

    def event(label: str, action) -> None:
        nonlocal max_seq
        if action is not None:
            action()
        time.sleep(SETTLE)
        changes = pull(client, subscriber, subscription)
        (FIXTURES / f"delta_{label}.json").write_text(
            json.dumps({"status": "ready", "changes": changes}, indent=2)
        )
        seqs = [c["seqNo"] for c in changes]
        assert all(
            sq > max_seq for sq in seqs
        ), f"seqNo not monotonic at {label}: {seqs}"
        if seqs:
            max_seq = max(seqs)
        summary.append(
            {
                "label": label,
                "count": len(changes),
                "types": sorted({c["type"] for c in changes}),
                "seqNos": seqs,
            }
        )

    event("00_baseline", None)

    def do_create():
        nonlocal file_id
        file_id = _mkfile(s, root, f"f-{tag}.txt")

    event("01_create_file", do_create)

    event(
        "02_edit_content",
        lambda: s.put(
            f"{CORE}/nodes/{file_id}/content",
            data=b"edited content bytes!!",
            headers={"Content-Type": "text/plain"},
        ),
    )

    event(
        "03_rename",
        lambda: s.put(
            f"{CORE}/nodes/{file_id}", data=json.dumps({"name": f"f-{tag}-renamed.txt"})
        ),
    )

    def do_subfolder():
        nonlocal subfolder_id
        subfolder_id = _mkfolder(s, root, f"sub-{tag}")

    event("04_create_subfolder", do_subfolder)

    event(
        "05_move",
        lambda: s.post(
            f"{CORE}/nodes/{file_id}/move",
            data=json.dumps({"targetParentId": subfolder_id}),
        ),
    )

    event("06_delete_file", lambda: s.delete(f"{CORE}/nodes/{file_id}"))
    event("07_delete_folder", lambda: s.delete(f"{CORE}/nodes/{subfolder_id}"))
    event("08_noop_after_drain", None)

    (FIXTURES / "capture_summary.json").write_text(
        json.dumps(
            {
                "subscriber": subscriber,
                "subscription": subscription,
                "folder": root,
                "max_seqNo": max_seq,
                "events": summary,
            },
            indent=2,
        )
    )

    # cleanup
    deprovision(s, subscriber)
    s.delete(f"{CORE}/nodes/{root}?permanent=true")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
