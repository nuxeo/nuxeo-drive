"""Maintenance script — deletes leftover test tenants / sites / users on the
Alfresco server.

Mirrors :mod:`tests.nuxeo.cleanup`. Not imported by tests; run manually::

    python -m tests.alfresco.cleanup
"""

from logging import basicConfig, getLogger

from tests import env_alfresco as env

log = getLogger(__name__)


def _client():
    """Build an authenticated Alfresco client using env-var credentials."""
    from alfresco import Alfresco, BasicAuth

    if not env.ALFRESCO_URL:
        raise SystemExit("ALFRESCO_URL is not set; refusing to run cleanup.")
    auth = BasicAuth(env.ALFRESCO_USER, env.ALFRESCO_PASSWORD)
    return Alfresco(url=env.ALFRESCO_URL, auth=auth)


def remove_old_test_folders(client) -> None:
    """Delete children of ``env.ALFRESCO_TEST_PATH`` whose names look like
    Drive test artefacts (prefixes ``ndt-`` or ``test_``).
    """
    try:
        parent = client.nodes.get_by_path(env.ALFRESCO_TEST_PATH)
    except Exception:
        log.warning(
            "Test folder %s does not exist; nothing to clean.", env.ALFRESCO_TEST_PATH
        )
        return

    children = client.nodes.list_children(parent.id)
    for entry in children:
        name = getattr(entry, "name", "") or ""
        if name.startswith(("ndt-", "test_")):
            client.nodes.delete(entry.id)
            log.info("Deleted old node %s (%s)", name, entry.id)


def remove_old_users(client) -> None:
    """Delete non-admin test users left over by previous runs."""
    try:
        people = client.people.list()
    except Exception:  # pragma: no cover
        log.warning("Cannot list Alfresco users; skipping user cleanup.")
        return

    for person in people:
        user_id = getattr(person, "id", "")
        if user_id.startswith("ndt-"):
            client.people.delete(user_id)
            log.info("Deleted old user %s", user_id)


def main() -> None:
    basicConfig(level="INFO", format="%(levelname)-7s %(name)s: %(message)s")
    client = _client()
    try:
        remove_old_test_folders(client)
        remove_old_users(client)
    finally:
        client.close()


if __name__ == "__main__":
    main()
