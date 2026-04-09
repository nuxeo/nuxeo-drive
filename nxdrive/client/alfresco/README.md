# Minimal Alfresco Client Skeleton

This module provides a minimal REST-based Alfresco client intended to help migrate from
Nuxeo-specific operations incrementally.

## Included

- `AlfrescoClient` in `nxdrive/client/alfresco/client.py`
- Runner in `nxdrive/client/alfresco/runner.py`
- Unit tests in `tests/unit/test_client_alfresco.py`

## Implemented methods

- `authenticate()`
- `list_nodes(parent_id="-root-")`
- `get_node(node_id)`
- `upload_file(parent_id, file_path, name="", auto_rename=True)`
- `delete_node(node_id, permanent=False)`
- `create_subscription(subscriber_id, target_path, subscription_type="BOTH")`
- `get_subscription(subscriber_id, subscription_id)`
- `start_subscription_sync(subscriber_id, subscriptions_query, json=...)`
- `get_subscription_sync(subscriber_id, subscriptions_query, sync_id)`
- `cancel_subscription_sync(subscriber_id, subscriptions_query, sync_id)`
- `get_sync_service()`
- `get_sync_service_configuration()`

## Quick try

```bash
python -m nxdrive.client.alfresco.runner --url "https://alfresco.example.com" --username "admin" --password "admin" auth
python -m nxdrive.client.alfresco.runner --url "https://alfresco.example.com" --token "<bearer-token>" list --parent-id "-root-"
```

Environment variable alternatives:

- `ALFRESCO_URL`
- `ALFRESCO_USERNAME`
- `ALFRESCO_PASSWORD`
- `ALFRESCO_TOKEN`
- `ALFRESCO_SYNC_URL`

## Notes

- This is intentionally small and does not yet mirror every method of `Remote`.
- No new dependency was added: this uses `requests`, which is already used in this repository.
- Private sync-service endpoints can target a separate base URL via `AlfrescoClient(..., sync_base_url="http://localhost:9090")` or the `ALFRESCO_SYNC_URL` environment variable.

## Integration Status (as of March 2026)

### ✅ Working
- Basic CRUD operations (create/read/update/delete files and folders)
- Folder creation with name validation
- File uploads with proper binary handling
- Node moves and renames via correct Alfresco endpoints
- Remote scanning and child enumeration
- Root folder synchronization
- Metadata URL building for UI integration
- Sync-service endpoint client support

### 🚧 In Progress
- Delta change tracking via Alfresco sync-service (endpoints ready, watcher integration pending)
- Subscription-based change polling (client methods added, AlfrescoRemote integration next)

### ❌ Not Yet Implemented
- Lock/unlock operations
- Undelete (trash) operations
- Personal space / "Locally Edited" concept
- Query/search operations
- Task management

## Known Limitations

- Change detection currently uses full remote scans (forced by `hasTooManyChanges=True`)
  - Will be replaced by proper delta sync via `/subscribers/{subscriberId}/subscriptions/.../sync` once subscription management is wired
- Some event types and security updates are placeholders
- Digest/hash algorithm mapping is minimal (Alfresco MIME types mapped, not cryptographic hashes)
