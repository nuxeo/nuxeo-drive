"""
Audit events.

Keep synced with:
- https://github.com/nuxeo/nuxeo/blob/master/modules/core/nuxeo-core-api/src/main/java/org/nuxeo/ecm/core/api/event/DocumentEventTypes.java
- https://github.com/nuxeo/nuxeo/blob/master/modules/platform/nuxeo-drive-server/nuxeo-drive-core/src/main/java/org/nuxeo/drive/service/NuxeoDriveEvents.java
"""  # noqa

DELETED_EVENT = "deleted"
DOCUMENT_LOCKED = "documentLocked"
DOCUMENT_MOVED = "documentMoved"
DOCUMENT_UNLOCKED = "documentUnlocked"
ROOT_REGISTERED = "rootRegistered"
SECURITY_UPDATED_EVENT = "securityUpdated"
