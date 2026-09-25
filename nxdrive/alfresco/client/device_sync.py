"""
Device Sync provisioning for an Alfresco engine.

Owns the state machine that gets an engine from "nothing" to "able to poll
the change feed":

1. probe the repository for the Device Sync AMP (``sync_amp``);
2. register a *subscriber* for this device (or reuse the persisted one);
3. resolve the subscriber's *syncer* to learn the standalone Sync Service
   URL and bind it onto the client;
4. create a *subscription* on the sync root (or reuse the persisted one).

Every identifier is persisted in the engine DAO ``Config`` table so a
restart reuses the same subscriber/subscription instead of leaking new ones.

The Sync Service itself (``start_sync`` / ``get_sync`` / ``clear_sync``) is
driven by :class:`~nxdrive.alfresco.engine.watcher.remote_watcher.AlfrescoRemoteWatcher`;
this module only provisions.
"""

from logging import getLogger
from typing import TYPE_CHECKING, Optional

import alfresco
from alfresco.exceptions import AlfrescoError, NotFoundError

if TYPE_CHECKING:
    from nxdrive.alfresco.client.remote import AlfrescoRemote
    from nxdrive.drive.dao.engine import EngineDAO

__all__ = ("DEVICE_SYNC_CLIENT_VERSION", "DeviceSyncProvisioner")

log = getLogger(__name__)

#: Version advertised to Device Sync when registering a subscriber and when
#: starting a sync. This is the ``alfresco-rest-client`` library version, not
#: the Drive application version: the repository validates it against its own
#: ``dsyncClientVersionMin`` floor and rejects anything below it.
DEVICE_SYNC_CLIENT_VERSION = alfresco.__version__

#: DAO ``Config`` keys holding the provisioned Device Sync identifiers.
CONF_SUBSCRIBER_ID = "device_sync_subscriber_id"
CONF_SERVICE_ID = "device_sync_service_id"
CONF_SERVICE_URL = "device_sync_service_url"
CONF_SUBSCRIPTION_ID = "device_sync_subscription_id"

#: Subscription whose existing content has already been seeded into the DAO.
#: Holds a subscription id (not a flag) so a re-subscription seeds again.
CONF_BOOTSTRAPPED_FOR = "device_sync_bootstrapped_for"

#: Subscription kind requested from the AMP.
SUBSCRIPTION_TYPE = "CONTENT"


class DeviceSyncProvisioner:
    """Provision and persist the Device Sync identifiers for one engine."""

    def __init__(
        self,
        remote: "AlfrescoRemote",
        dao: "EngineDAO",
        /,
        *,
        device_os: str,
        client_version: str = DEVICE_SYNC_CLIENT_VERSION,
    ) -> None:
        self.remote = remote
        self.dao = dao
        self.device_os = device_os
        self.client_version = client_version

        self.subscriber_id: str = ""
        self.subscription_id: str = ""

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__} "
            f"subscriber={self.subscriber_id!r}, "
            f"subscription={self.subscription_id!r}>"
        )

    @property
    def provisioned(self) -> bool:
        return bool(self.subscriber_id and self.subscription_id)

    # -- Entry point ---------------------------------------------------------

    def provision(self, root_node_id: str, /) -> bool:
        """Ensure a subscriber, Sync Service URL and subscription exist.

        Returns ``True`` when the engine is ready to poll the change feed.
        Any failure is logged and returns ``False`` — the caller decides what
        to do, there is deliberately no silent fallback.
        """
        if not self._check_amp_available():
            return False

        subscriber_id = self._ensure_subscriber()
        if not subscriber_id:
            return False

        if not self._ensure_service_url(subscriber_id):
            return False

        subscription_id = self._ensure_subscription(subscriber_id, root_node_id)
        if not subscription_id:
            return False

        self.subscriber_id = subscriber_id
        self.subscription_id = subscription_id
        log.info(
            f"Device Sync ready for root_node_id={root_node_id!r} "
            f"(device_os={self.device_os!r}, client_version={self.client_version!r}, "
            f"subscriber={subscriber_id!r}, subscription={subscription_id!r})"
        )
        return True

    # -- Step 1: capability probe --------------------------------------------

    def _check_amp_available(self) -> bool:
        """Probe the repository for the Device Sync AMP endpoints."""
        try:
            available = self.remote.device_sync_available()
        except AlfrescoError:
            log.exception(
                "Could not determine whether the Device Sync AMP is "
                "installed (transport failure)"
            )
            return False

        if not available:
            log.error(
                "The Device Sync AMP is not installed on "
                f"{self.remote.server_url!r} — the change feed is unavailable"
            )
            return False

        return True

    # -- Step 2: subscriber ---------------------------------------------------

    def _ensure_subscriber(self) -> str:
        """Return a usable subscriber id, creating one if needed."""
        stored = self.dao.get_config(CONF_SUBSCRIBER_ID)
        if stored:
            try:
                subscriber = self.remote.client.sync_amp.get_subscriber(stored)
            except NotFoundError:
                log.warning(
                    f"Stored subscriber {stored!r} no longer exists on the "
                    "server — registering a new one"
                )
            except AlfrescoError:
                log.exception(f"Could not validate subscriber {stored!r}")
                return ""
            else:
                log.debug(
                    f"Reusing subscriber {subscriber.id!r} "
                    f"(syncServiceId={subscriber.sync_service_id!r})"
                )
                self.dao.update_config(CONF_SERVICE_ID, subscriber.sync_service_id)
                return subscriber.id

        return self._create_subscriber()

    def _create_subscriber(self) -> str:
        """Register a new subscriber and persist its id immediately.

        The AMP assigns the id and accepts no client-supplied identifier, so
        registration is not idempotent: a crash between the call returning and
        the id being persisted orphans a subscriber. The persist therefore
        happens before anything else can fail.
        """
        try:
            subscriber = self.remote.client.sync_amp.create_subscriber(
                self.device_os, self.client_version
            )
        except AlfrescoError:
            log.exception("Failed to register a Device Sync subscriber")
            return ""

        if not subscriber.id:
            log.error(f"Server returned a subscriber with no id: {subscriber!r}")
            return ""

        self.dao.update_config(CONF_SUBSCRIBER_ID, subscriber.id)
        self.dao.update_config(CONF_SERVICE_ID, subscriber.sync_service_id)
        # A new subscriber invalidates any subscription of its predecessor.
        self.dao.update_config(CONF_SUBSCRIPTION_ID, None)
        log.debug(
            f"Registered subscriber {subscriber.id!r} "
            f"(syncServiceId={subscriber.sync_service_id!r})"
        )
        return subscriber.id

    # -- Step 3: Sync Service URL --------------------------------------------

    def _ensure_service_url(self, subscriber_id: str, /) -> bool:
        """Resolve the syncer URI for *subscriber_id* and bind it."""
        syncer_id = self.dao.get_config(CONF_SERVICE_ID)
        if not syncer_id:
            log.error(f"No syncServiceId recorded for subscriber {subscriber_id!r}")
            return False

        try:
            syncer = self.remote.client.sync_amp.get_syncer(syncer_id)
        except AlfrescoError:
            log.exception(f"Failed to resolve syncer {syncer_id!r}")
            return False

        if not syncer.uri:
            log.error(f"Syncer {syncer_id!r} reports no URI: {syncer!r}")
            return False

        log.debug(
            f"Syncer {syncer_id!r} -> {syncer.uri!r} "
            f"(repo={syncer.repo_info.version_label!r}, "
            f"min client={syncer.dsync_client_version_min!r})"
        )
        self.remote.set_sync_service_url(syncer.uri)
        self.dao.update_config(CONF_SERVICE_URL, syncer.uri)

        if not self._check_service_reachable():
            return False

        return True

    def _check_service_reachable(self) -> bool:
        try:
            reachable = self.remote.sync_service_reachable()
        except AlfrescoError:
            log.exception("Sync Service healthcheck raised")
            return False

        if not reachable:
            log.error(
                f"Sync Service at {self.remote.sync_service_url!r} is not reachable"
            )
            return False

        return True

    # -- Step 4: subscription -------------------------------------------------

    def _ensure_subscription(self, subscriber_id: str, root_node_id: str, /) -> str:
        """Return a usable subscription id for *root_node_id*."""
        stored = self.dao.get_config(CONF_SUBSCRIPTION_ID)
        if stored:
            try:
                subscription = self.remote.client.sync_amp.get_subscription(
                    subscriber_id, stored
                )
            except NotFoundError:
                log.warning(
                    f"Stored subscription {stored!r} no longer exists — "
                    "creating a new one"
                )
            except AlfrescoError:
                log.exception(f"Could not validate subscription {stored!r}")
                return ""
            else:
                if subscription.target_node_id == root_node_id:
                    log.debug(
                        f"Reusing subscription {subscription.id!r} "
                        f"(target={subscription.target_node_id!r}, "
                        f"state={subscription.state!r})"
                    )
                    return subscription.id
                log.warning(
                    f"Stored subscription {stored!r} targets "
                    f"{subscription.target_node_id!r}, expected {root_node_id!r} — "
                    "recreating"
                )
                self._delete_subscription(subscriber_id, stored)

        return self._create_subscription(subscriber_id, root_node_id)

    def _create_subscription(self, subscriber_id: str, root_node_id: str, /) -> str:
        try:
            subscription = self.remote.client.sync_amp.create_subscription(
                subscriber_id, root_node_id, SUBSCRIPTION_TYPE
            )
        except AlfrescoError:
            log.exception(f"Failed to subscribe {subscriber_id!r} to {root_node_id!r}")
            return ""

        if not subscription.id:
            log.error(f"Server returned a subscription with no id: {subscription!r}")
            return ""

        self.dao.update_config(CONF_SUBSCRIPTION_ID, subscription.id)
        log.debug(
            f"Created subscription {subscription.id!r} on "
            f"{subscription.target_path or root_node_id!r} "
            f"(state={subscription.state!r})"
        )
        return subscription.id

    # -- Reset / teardown ------------------------------------------------------

    def resubscribe(self, root_node_id: str, /) -> bool:
        """Drop and recreate the subscription so the server replays everything.

        This is the response to a ``resets`` entry: the server has told us our
        view is stale, and a fresh subscription is how Device Sync re-sends the
        full content as ``CREATE`` changes.
        """
        log.warning(f"Re-subscribing to {root_node_id!r} after a server-side reset")
        if self.subscriber_id and self.subscription_id:
            self._delete_subscription(self.subscriber_id, self.subscription_id)

        self.dao.update_config(CONF_SUBSCRIPTION_ID, None)
        self.subscription_id = ""

        subscription_id = self._create_subscription(self.subscriber_id, root_node_id)
        if not subscription_id:
            return False

        self.subscription_id = subscription_id
        return True

    def _delete_subscription(self, subscriber_id: str, subscription_id: str, /) -> None:
        try:
            self.remote.client.sync_amp.delete_subscription(
                subscriber_id, subscription_id
            )
            log.debug(f"Deleted subscription {subscription_id!r}")
        except AlfrescoError:
            # Deleting a subscription whose target node was permanently
            # removed fails server-side with HTTP 400; never fatal here.
            log.warning(
                f"Could not delete subscription {subscription_id!r}",
                exc_info=True,
            )

    def teardown(self) -> None:
        """Remove this device's server-side Device Sync state.

        Subscriptions are deleted before their subscriber: the AMP rejects
        deleting a subscription whose target node is already gone, and
        deleting the subscriber first would strand them.
        """
        subscriber_id = self.subscriber_id or self.dao.get_config(CONF_SUBSCRIBER_ID)
        subscription_id = self.subscription_id or self.dao.get_config(
            CONF_SUBSCRIPTION_ID
        )
        log.debug(
            f"Tearing down subscriber={subscriber_id!r} "
            f"subscription={subscription_id!r}"
        )

        if subscriber_id and subscription_id:
            self._delete_subscription(subscriber_id, subscription_id)

        if subscriber_id:
            try:
                self.remote.client.sync_amp.delete_subscriber(subscriber_id)
                log.debug(f"Deleted subscriber {subscriber_id!r}")
            except AlfrescoError:
                log.warning(
                    f"Could not delete subscriber {subscriber_id!r}",
                    exc_info=True,
                )

        for key in (
            CONF_SUBSCRIBER_ID,
            CONF_SERVICE_ID,
            CONF_SERVICE_URL,
            CONF_SUBSCRIPTION_ID,
            CONF_BOOTSTRAPPED_FOR,
        ):
            self.dao.update_config(key, None)

        self.subscriber_id = ""
        self.subscription_id = ""

    # -- Orphan recovery -------------------------------------------------------

    def cleanup_orphans(self, *, keep_id: Optional[str] = None) -> int:
        """Delete this user's other subscribers, returning how many were removed.

        ``create_subscriber`` accepts no client-supplied identifier, so a crash
        between registration and persisting the id orphans a subscriber with no
        way to recognise it later. ``list_subscribers`` is scoped to the
        authenticated user, so everything it returns belongs to us; anything
        that is not the subscriber we are actually using is stale.

        Not called automatically — device-per-user is not one-to-one (the same
        account may legitimately run Drive on several machines), so this would
        delete other machines' subscribers. Exposed for manual recovery.
        """
        keep = keep_id or self.subscriber_id
        removed = 0
        try:
            subscribers = list(self.remote.client.sync_amp.iter_subscribers())
        except AlfrescoError:
            log.exception("Could not list subscribers for orphan cleanup")
            return 0

        for subscriber in subscribers:
            if subscriber.id == keep:
                continue
            try:
                self.remote.client.sync_amp.delete_subscriber(subscriber.id)
            except AlfrescoError:
                log.warning(
                    f"Could not delete orphan subscriber {subscriber.id!r}",
                    exc_info=True,
                )
            else:
                removed += 1
                log.debug(f"Deleted orphan subscriber {subscriber.id!r}")

        log.debug(f"Orphan cleanup removed {removed} subscriber(s)")
        return removed
