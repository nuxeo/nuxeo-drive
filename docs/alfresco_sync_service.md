# Alfresco Enterprise Sync Service — Delta Change Feed (Phase 0 findings)

Enterprise-only remote-change detection for the Alfresco engine. This replaces the
O(total-tree) full recursive scan with an O(changes) change-log (parity with Nuxeo's
`GetChangeSummary`), using the Alfresco **Enterprise Sync Service (dsync)**.

Phase 0 was a live spike against **ACS 26.1.0 Enterprise** (`:8080`) + **service-sync
5.3.2** (`:9090`), admin/admin, IdP/Keycloak disabled (NTLM chain, so basic auth worked).
Everything below was verified end-to-end; real captured payloads live in
`tests/alfresco/sync_service/fixtures/` and the capture harness is
`tests/alfresco/sync_service/capture_deltas.py`.

> The `alfresco-rest-client` library's original `SyncServiceAPI`/`SyncServiceAMPAPI` were
> **entirely wrong** (speculative endpoints, all 404; the AMP webscripts
> `/alfresco/s/enterprise/sync/v1/*` are not even installed). Library **1.0.2** corrects
> the endpoints to what is documented here.

## 1. Discovery / capability detection

`GET {repo}:8080/alfresco/s/devicesync/config` (see `fixtures/repo_devicesync_config.json`)
returns the sync-service base `uri` and repo edition. `GET {sync_uri}/config/syncService`
(see `fixtures/syncservice_config.json`) returns service version, filters, and
`dsyncClientVersionMin`.

Gate the feature on:
- `repoInfo.edition == "Enterprise"`
- a reachable `uri` (the standalone sync service)
- client version >= `dsyncClientVersionMin` (observed `"1.0.1"`)

## 2. Sync Service API (`:9090`)

- Base prefix: `{sync_uri}/api/-default-/private/alfresco/versions/1`
  where `sync_uri` = the `uri` from `devicesync/config` (e.g. `http://localhost:9090/alfresco`).
- Health: `GET {sync_uri}/healthcheck` (unauthenticated, **outside** the prefix).
- Only one Jersey resource — `SyncResource`:
  - `GET  /config/syncService`
  - `POST   .../subscribers/{subscriberId}/subscriptions/{subscriptionId}/sync`      (start)
  - `GET    .../subscribers/{subscriberId}/subscriptions/{subscriptionId}/sync/{syncId}` (poll)
  - `DELETE .../subscribers/{subscriberId}/subscriptions/{subscriptionId}/sync/{syncId}` (ack/clear)

### Async two-step pull
1. `start_sync(subscriberId, subscriptionId, {"clientVersion":"1.0.1","changes":[]})`
   → `SyncStatus(sync_id, status="ok")`.
   **Both** body fields are mandatory. A missing/low `clientVersion` → HTTP 400/401
   `"Incompatible client version"`.
2. Poll `get_sync(subscriberId, subscriptionId, syncId)` until
   `status in ("ready","error")`. On `ready` the body carries `changes[]`
   (and `moreChanges`, `resets[]`, `missing/staleSubscriptionIds`, `url`).
3. `clear_sync(subscriberId, subscriptionId, syncId)` acknowledges the batch and advances
   the server-side marker so the next pull returns only newer changes.

If the subscription is unknown the poll returns
`{"status":"error","message":"The following subscriptionIds are unknown: [...]"}`
(see `fixtures/sync_result_unknown_subscription.json`).

## 3. Device registration is a REPOSITORY operation (not a sync-service call)

This was the missing piece the previous client code omitted. Provision on the **repo**
private v1 API (`:8080/alfresco/api/-default-/private/alfresco/versions/1`):

1. `POST /subscribers {"deviceOS":"darwin","clientVersion":"1.0.1"}` → `entry.id` = **subscriberId**.
2. `POST /subscribers/{subscriberId}/subscriptions
   {"targetNodeId":"<folderId>","subscriptionType":"BOTH"}` → `entry.id` = **subscriptionId**
   (state `VALID`).

`subscriptionType` enum = `CONTENT | METADATA | BOTH`. NodeSubscription fields:
`state, targetPath, subscriptionType, createdAt, deviceSubscriptionId, id, targetNodeId`.
Backing content model = `devicesync:*` (subscriber aspect, `deviceSubscriptions`,
`nodeSubscriptions` types). Persist `subscriberId` + `subscriptionId` (+ last `seqNo`)
on the client and reuse across restarts; re-provision on `missing`/stale/`resets`.

**Propagation lag:** repo → ActiveMQ `alfresco.repo.event2` → sync service
(`EventToChangeMapper`). After creating a subscription there is a ~seconds delay before the
first sync succeeds (otherwise `status:error "subscriptionIds are unknown"`), and each change
appears ~0.5–1.5 s after the action. The capture harness uses a per-event drain loop.

## 4. Change entry shape (verified)

Wire fields: `type, nodeId, seqNo, name, toName, path, toPath, parentNodeIds[],
toParentNodeIds[], checksum, size, nodeType, aspects[], eventTimestamp, nodeTimestamp,
username, conflict, skip, error, folderChange, cascade, async, ...`.

Verified event → type mapping (see matching `fixtures/delta_*.json`):

| Action        | `type`         | Notable fields                                              |
|---------------|----------------|-------------------------------------------------------------|
| create file   | `CREATE_REPOS` | `path`, full `parentNodeIds`; `size:-1`                     |
| edit content  | `UPDATE_REPOS` | real `size` (bytes)                                         |
| rename        | `RENAME_REPOS` | `name`→`toName`, `path`→`toPath`                            |
| create folder | `CREATE_REPOS` | `folderChange`/folder nodeType                              |
| move          | `MOVE_REPOS`   | `parentNodeIds`→`toParentNodeIds`, `path`→`toPath`          |
| delete        | `DELETE_REPOS` | tombstone: `nodeId` + last `path`; `username:null`          |

- `nodeId` is **stable** across rename/move/delete → reliable identity for the DAO mapping.
- `parentNodeIds` = full ancestor chain (nearest parent first) → cheap subtree filtering.
- Marker = **`seqNo`**, monotonic per subscription; `clear_sync` acks so a drained pull
  returns 0 changes (verified, no duplicate seqNos).

### Corrections to earlier jar-only assumptions (IMPORTANT)
1. `checksum` is always the literal string `"dummyChecksum"` — **not** a content hash.
   Content-change detection must still use `UPDATE_REPOS` + `size` + timestamps (the
   existing watcher's timestamp approach stays necessary).
2. Wire `type` is coarser than the full `ChangeType` enum — content edits arrive as generic
   `UPDATE_REPOS`, not `UPDATE_CONTENT_REPOS`.
3. `size` is real only on content change; `-1` for metadata-only / folders / tombstones.

### Full `ChangeType` enum (from `service-sync-5.3.2.jar`, for reference)
server→client: `CREATE_REPOS, DELETE_REPOS, MOVE_REPOS, RENAME_REPOS,
RENAME_UPDATE_REPOS, UPDATE_REPOS, UPDATE_CONTENT_REPOS, UPDATE_METADATA_REPOS`;
client→server: the `*_LOCAL` variants; plus `RESET, SUBSCRIBE, UNSUBSCRIBE, ERROR` and
lock/checkout/permission/group/records types.

## 5. Known gaps / open items

- **Library `SyncStatus` (1.0.2)** parses only `sync_id/status/message/more_changes`; the
  delta payload (`changes[]`, `resets[]`, `missing/staleSubscriptionIds`, `url`) survives
  only in `SyncStatus._raw`. Phase 1 needs a typed `changes: list[Change]` + a `Change`
  model (or client-side `_raw` consumption).
- **Auth on Identity-Service (Keycloak) deployments** is unverified — this test env had IdP
  disabled so basic auth worked for sync pulls. Must confirm token flow into the
  sync-service origin.
- **Server scaling:** the standalone service is stateful per-subscriber
  (`SQLChangesDAO` materialises per-subscription change tables) and does not scale
  horizontally. A future server improvement would be a stateless marker endpoint in the
  repo reusing `event2`; out of scope for the client work.

## 6. Exit criteria — verdict

Met: tombstones ✅, moves/renames with stable identity ✅, resumable `seqNo` marker ✅,
ACL/subtree scoping via `parentNodeIds` ✅, device provisioning solved ✅.
Not met / deferred: real content hash (server sends a dummy), OAuth-origin auth (untested).

Phase 0 is COMPLETE. See the master plan (session `plan.md`) for Phase 1 (client change
provider) design.
