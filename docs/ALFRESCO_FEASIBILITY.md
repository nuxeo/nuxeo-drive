# Feasibility: Nuxeo Drive Integration with Alfresco (REST API + Sync Service)

## Scope

This document evaluates feasibility of running Nuxeo Drive against Alfresco by using:

- Alfresco Public REST API (`/public/alfresco/versions/1`)
- Alfresco Private Sync Service API (`/private/alfresco/versions/1`)
- `AlfrescoRemote` as the `Remote`-contract adapter layer

It also lists method-level mappings from Nuxeo `Remote` API to Alfresco implementations.

## Executive Feasibility Summary

**Overall feasibility: High for MVP, Medium for production parity.**

- **MVP is feasible now** for authentication, browsing, metadata reads, create/update/delete, upload/download basics,
  and recursive full-scan sync fallback.
- **Production parity requires Phase 2** mainly around delta synchronization semantics, locking, query translation, and
  sync-root management.
- **Alfresco Sync Service is feasible** as the long-term replacement for fallback full scans, but needs wiring from
  `get_changes()` and robust cursor/retry handling.
- **IdP-only authentication is feasible** if Alfresco exposes API-usable bearer tokens or sessions for both Public REST
  and Sync Service endpoints; see `docs/ALFRESCO_IDP_AUTH.md`.

## Integration Architecture

- `nxdrive/client/alfresco_remote.py`: Nuxeo `Remote`-compatible adapter.
- `nxdrive/client/alfresco/client.py`: low-level Alfresco REST + Sync Service HTTP client.
- Current sync behavior:
    - Descendants scroll is disabled for Alfresco (`canScrollDescendants=False`).
    - Watcher uses recursive scans and paginated children traversal.
    - `get_changes()` currently forces full-scan behavior (`hasTooManyChanges=True`) instead of true deltas.

## Related Auth Note

For SSO / external identity-provider deployments, see `docs/ALFRESCO_IDP_AUTH.md`.
That note explains the main difference between:

- **Nuxeo + IdP**: Nuxeo Drive authenticates through Nuxeo-native flows that the client already understands.
- **Alfresco + IdP**: the adapter must convert browser/IdP authentication into credentials that Alfresco Public REST and
  Sync Service APIs will accept.

## Method Mapping: Nuxeo `Remote` -> Alfresco

Status legend:

- `Implemented`: production code path exists and is used.
- `Partial`: implemented as fallback/compatibility, not full parity.
- `No-op`: method exists for contract compatibility only.
- `Not Implemented`: raises `NotImplementedError`.

| Nuxeo `Remote` method        | Alfresco mapping                                                 | Status          | Notes                                                                           |
|------------------------------|------------------------------------------------------------------|-----------------|---------------------------------------------------------------------------------|
| `cancel_batch()`             | No Alfresco batch API call                                       | No-op           | Kept for contract compatibility.                                                |
| `check_integrity()`          | None                                                             | No-op           | Integrity validation not yet enforced in adapter.                               |
| `check_integrity_simple()`   | None                                                             | No-op           | Same as above.                                                                  |
| `check_ref()`                | Identity mapping                                                 | Implemented     | Returns given ref unchanged.                                                    |
| `custom_global_metrics`      | Empty dict                                                       | No-op           | Metrics bridge pending.                                                         |
| `delete()`                   | `DELETE /nodes/{id}` via `AlfrescoClient.delete_node()`          | Implemented     | Uses Alfresco node deletion.                                                    |
| `download()`                 | None                                                             | Not Implemented | Adapter requires `stream_content()` path instead.                               |
| `escape()`                   | Local string escaping helper                                     | Implemented     | Compatibility utility.                                                          |
| `escapeCarriageReturn()`     | Local string escaping helper                                     | Implemented     | Compatibility utility.                                                          |
| `execute()`                  | None                                                             | Not Implemented | Explicitly unsupported in adapter.                                              |
| `exists()`                   | `GET /nodes/{id}`                                                | Implemented     | Returns boolean by request success/failure.                                     |
| `exists_in_parent()`         | `GET /nodes/{parent}/children` + name check                      | Implemented     | Folderish argument ignored for now.                                             |
| `expand_sync_root_name()`    | Returns input item                                               | No-op           | No Alfresco-specific expansion yet.                                             |
| `fetch()`                    | `GET /nodes/{id}`                                                | Implemented     | Returns raw entry/document dict shape.                                          |
| `filter_schema()`            | Returns `[]`                                                     | Partial         | Contract-safe for GUI; no schema filtering logic.                               |
| `get_blob()`                 | `GET /nodes/{id}/content`                                        | Partial         | Returns bytes from placeholder conversion path.                                 |
| `get_changes()`              | Full-scan trigger object                                         | Partial         | Returns `hasTooManyChanges=True` to force full remote scan; no true deltas yet. |
| `get_config_types()`         | Empty dict                                                       | Partial         | Type model discovery not mapped.                                                |
| `get_doc_enricher()`         | Returns `[]`                                                     | Partial         | Avoids GUI type errors; no subtype enrichment from Alfresco model yet.          |
| `get_filesystem_root_info()` | `get_fs_item("-root-")` or synthetic root fallback               | Implemented     | Handles deployments where root GET is unavailable.                              |
| `get_fs_children()`          | Paginated `GET /nodes/{id}/children`                             | Implemented     | Uses `_list_all_children_entries()` to gather all pages.                        |
| `get_fs_info()`              | Wrapper over `get_fs_item()`                                     | Implemented     | Raises NotFound for deleted/missing nodes.                                      |
| `get_fs_item()`              | `GET /nodes/{id}`                                                | Implemented     | Maps Alfresco node to `RemoteFileInfo` shape.                                   |
| `get_info()`                 | `get_fs_item()` + Nuxeo document projection                      | Implemented     | Produces `NuxeoDocumentInfo`-compatible object.                                 |
| `get_note()`                 | None                                                             | Not Implemented | Note document mapping pending.                                                  |
| `get_server_configuration()` | Static `{"product": "alfresco", "version": "unknown"}`           | Partial         | Version discovery not dynamic yet.                                              |
| `is_filtered()`              | DAO filter check                                                 | Implemented     | Reuses existing local filtering behavior.                                       |
| `is_sync_root()`             | Parent is `-root-`                                               | Partial         | Simplified rule, no server-side sync-root semantics.                            |
| `lock()`                     | None                                                             | Not Implemented | Alfresco lock mapping pending.                                                  |
| `make_folder()`              | `POST /nodes/{parent}/children` (`nodeType=cm:folder`)           | Implemented     | Handles 409 by reusing existing folder if found.                                |
| `move()`                     | `POST /nodes/{id}/move`                                          | Implemented     | Uses `targetParentId`.                                                          |
| `move2()`                    | `POST /nodes/{id}/move` with rename payload                      | Implemented     | Supports move+rename compatibility flow.                                        |
| `personal_space()`           | Path lookup (`/User Homes/{user}`) -> fallback `GET /nodes/-my-` | Implemented     | Graceful fallback to placeholder when unresolved.                               |
| `query()`                    | None                                                             | Not Implemented | NXQL-to-Alfresco translation not implemented.                                   |
| `register_as_root()`         | None                                                             | Not Implemented | No native Alfresco sync-root registration equivalent.                           |
| `reload_global_headers()`    | None                                                             | No-op           | Header reload not needed for current client.                                    |
| `rename()`                   | `PUT /nodes/{id}` with `{"name": ...}`                           | Implemented     | Direct Alfresco rename.                                                         |
| `request_token()`            | `POST /authentication/.../tickets`                               | Implemented     | Stores Alfresco ticket token.                                                   |
| `revoke_token()`             | Local token clear                                                | Partial         | No server-side revoke endpoint used.                                            |
| `scroll_descendants()`       | Paginated direct children (`/children`) only                     | Partial         | Compatibility fallback; true descendants scroll unsupported.                    |
| `set_proxy()`                | Local proxy assignment                                           | Partial         | Adapter stores proxy; transport-level plumbing is limited.                      |
| `stream_content()`           | `GET /nodes/{id}/content`                                        | Partial         | Placeholder content write path; binary pipeline hardening pending.              |
| `stream_file()`              | `POST /nodes/{parent}/children` multipart upload                 | Implemented     | Supports `relativePath` forwarding.                                             |
| `stream_update()`            | `PUT /nodes/{id}/content` (raw octet-stream)                     | Implemented     | Correct Alfresco content update semantics.                                      |
| `transfer_end_callback()`    | None                                                             | No-op           | Callback kept for compatibility.                                                |
| `transfer_start_callback()`  | None                                                             | No-op           | Callback kept for compatibility.                                                |
| `undelete()`                 | None                                                             | Not Implemented | Depends on Alfresco trash APIs/version specifics.                               |
| `unlock()`                   | None                                                             | Not Implemented | Lock/unlock semantics pending.                                                  |
| `unregister_as_root()`       | None                                                             | Not Implemented | Same sync-root limitation as register.                                          |
| `update_token()`             | Local token update                                               | Implemented     | Updates both adapter and client token values.                                   |
| `upload()`                   | `POST /nodes/{parent}/children` via `upload_file()`              | Implemented     | Resolves `parentId`, supports `relativePath`.                                   |
| `upload_folder()`            | Delegates to `upload_folder_type()`                              | Implemented     | Compatibility wrapper.                                                          |
| `upload_folder_type()`       | `POST /nodes/{parent}/children` (`cm:folder`)                    | Implemented     | Includes validation + 404 mapping to NotFound.                                  |

## Alfresco Sync Service Mapping (Client-Level)

These methods exist in `AlfrescoClient` and are the base for delta-sync implementation:

| Client method                      | Endpoint                                                                   | Current use                               |
|------------------------------------|----------------------------------------------------------------------------|-------------------------------------------|
| `get_sync_service()`               | `GET /private/alfresco/versions/1/config/syncService`                      | Available, not yet central in engine loop |
| `get_sync_service_configuration()` | `GET /private/alfresco/versions/1/config/syncServiceConfiguration`         | Available                                 |
| `create_subscription()`            | `POST /private/.../subscribers/{id}/subscriptions`                         | Available                                 |
| `get_subscription()`               | `GET /private/.../subscribers/{id}/subscriptions/{subscriptionId}`         | Available                                 |
| `start_subscription_sync()`        | `POST /private/.../subscribers/{id}/subscriptions/{query}/sync`            | Available                                 |
| `get_subscription_sync()`          | `GET /private/.../subscribers/{id}/subscriptions/{query}/sync/{syncId}`    | Available                                 |
| `cancel_subscription_sync()`       | `DELETE /private/.../subscribers/{id}/subscriptions/{query}/sync/{syncId}` | Available                                 |

## Feasibility by Delivery Phase

### Phase 1 (MVP) - Feasible now

- Authentication and session token flow
- Browse/list tree structure with pagination
- Upload/update/delete/rename/move operations
- Folder picker and personal space fallback behavior
- Recursive full scans when delta stream is unavailable

### Phase 2 (Parity) - Required for production equivalence

- Real delta provider in `get_changes()` using Sync Service subscriptions
- Robust binary download/upload pipeline hardening in `stream_content()` / `get_blob()`
- Lock/unlock mapping
- Query translation (`NXQL -> Alfresco search`)
- Sync-root registration semantics (or documented alternative)
- Rich subtype/config type enrichment for direct-transfer UX

## Key Risks and Mitigations

- **Delta sync gap (High)**: currently full-scan fallback; can increase server/client load.
    - Mitigation: wire Sync Service subscription lifecycle into watcher loop.
- **Behavioral parity gaps (Medium)**: lock/query/sync-root not yet mapped.
    - Mitigation: implement explicit feature flags and graceful UI messaging.
- **Content stream placeholders (Medium)**: some binary flows still compatibility-level.
    - Mitigation: align stream APIs with strict binary responses and checksums.

## Conclusion

Integration is **feasible and already functional for MVP-level file synchronization workflows** using Alfresco REST.

To achieve Nuxeo-level parity in large or high-change environments, implement Sync Service-backed deltas and close the
remaining capability gaps listed in Phase 2.
