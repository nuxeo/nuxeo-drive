"""Cleanup old test users and workspaces."""
import env
from nuxeo.client import Nuxeo


def remove_old_ws(server: Nuxeo) -> None:
    docs = server.documents.get_children(path=env.WS_DIR)
    for doc in docs:
        if doc.title.startswith(("ndt-", "test_")):
            doc.delete()
            print(f"Deleted old {doc}")


def remove_old_users(server: Nuxeo) -> None:
    op = server.operations.new("User.Query")
    op.params = {"username": "ndt-%"}
    for user in op.execute()["users"]:
        server.users.delete(user["username"])
        print(f"Deleted old {user}")


auth = (env.NXDRIVE_TEST_USERNAME, env.NXDRIVE_TEST_PASSWORD)
server = Nuxeo(host=env.NXDRIVE_TEST_NUXEO_URL, auth=auth)
server.client.set(schemas=["dublincore"])

remove_old_ws(server)
remove_old_users(server)
