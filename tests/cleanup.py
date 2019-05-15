"""Cleanup old test users and workspaces."""
import os

from nuxeo.client import Nuxeo


def remove_old_ws(server: Nuxeo) -> None:
    docs = server.documents.get_children(path="/default-domain/workspaces")
    for doc in docs:
        if doc.title.startswith(("ndt-", "test_")):
            print(f"Deleting old {doc}")
            doc.delete()


def remove_old_users(server: Nuxeo) -> None:
    op = server.operations.new("User.Query")
    op.params = {"username": "ndt-%"}
    for user in op.execute()["users"]:
        print(f"Deleting old {user}")
        server.users.delete(user["username"])


url = os.getenv("NXDRIVE_TEST_NUXEO_URL", "http://localhost:8080/nuxeo")
auth = ("Administrator", "Administrator")
server = Nuxeo(host=url, auth=auth)
server.client.set(schemas=["dublincore"])

remove_old_ws(server)
remove_old_users(server)
