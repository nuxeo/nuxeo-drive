# coding: utf-8
import os
from logging import getLogger
from typing import Callable
from uuid import uuid4

import pytest
from faker import Faker
from nuxeo.client import Nuxeo
from nuxeo.documents import Document
from nuxeo.users import User

from nxdrive.manager import Manager


DEFAULT_NUXEO_URL = "http://localhost:8080/nuxeo"
log = getLogger(__name__)


@pytest.fixture(scope="session")
def faker() -> Callable[[], Faker]:
    """
    Get a Faker object to simplify other object creation.
    Note the using fr_FR will break tests when the username contains accent.
    """

    def _faker(l10n: str = "en_US") -> Faker:
        return Faker(l10n)

    return _faker


@pytest.fixture(scope="session")
def nuxeo_url() -> str:
    """Retrieve the Nuxeo URL."""
    url = os.getenv("NXDRIVE_TEST_NUXEO_URL", DEFAULT_NUXEO_URL)
    url = url.split("#")[0]
    return url


@pytest.fixture(scope="session")
def version() -> str:
    import nxdrive

    return nxdrive.__version__


@pytest.fixture
def manager_factory(
    request, tempdir, nuxeo_url, user_factory, workspace_factory, server, set_acls
) -> Callable[[], Manager]:
    """Manager instance with automatic clean-up."""

    # The workspace is the same for all users of the same test
    ws = None

    def _make_manager(home: str = "", with_engine: bool = True):
        nonlocal ws

        manager = Manager(home=home or tempdir())
        request.addfinalizer(manager.close)
        log.debug(f"[FIXTURE] Created {manager}")
        engine = None

        if with_engine:
            if not ws:
                ws = workspace_factory()

            conf_folder = manager.home / "nuxeo-conf"
            user = user_factory()
            manager.bind_server(
                conf_folder, nuxeo_url, user.uid, user.password, start_engine=False
            )

            set_acls(user.uid, ws.path, readonly=False)

            # Enable the synchronization on the workspace
            operation = server.operations.new("NuxeoDrive.SetSynchronization")
            operation.params = {"enable": True}
            operation.input_obj = ws.path
            operation.execute(void_op=True)

            for uid, engine_ in manager.get_engines().items():
                engine = engine_

            return manager, engine, engine.local, engine.remote, ws

        return manager

    yield _make_manager


@pytest.fixture(scope="session")
def server(nuxeo_url):
    """
    Get the Nuxeo instance.

    For now, we do not allow to use another than Administrator:Administrator
    to prevent unexpected actions on critical servers.
    """
    from nxdrive.constants import APP_NAME

    app_name = f"{APP_NAME} tests"
    auth = ("Administrator", "Administrator")
    server = Nuxeo(host=nuxeo_url, auth=auth, app_name=app_name)
    server.client.set(schemas=["dublincore"])
    return server


@pytest.fixture
def user_factory(request, server, faker):
    """User creation factory with automatic clean-up."""

    fake = faker()
    company = fake.company()
    company_domain = (
        company.lower().replace(",", "_").replace(" ", "_").replace("-", "_")
    )

    def _make_user(password: str = "Administrator"):
        first_name, last_name = fake.name().split(" ", 1)
        username = first_name.lower()
        properties = {
            "lastName": last_name,
            "firstName": first_name,
            "email": f"{username}@{company_domain}.org",
            "company": company,
            "password": password,
            "username": username,
        }

        user = server.users.create(User(properties=properties))
        request.addfinalizer(user.delete)
        log.debug(f"[FIXTURE] Created {user}")

        # Convenient attributes
        for k, v in properties.items():
            setattr(user, k, v)

        return user

    yield _make_user


@pytest.fixture
def workspace_factory(request, server):
    """Workspace creation factory with automatic clean-up."""

    def _make_workspace(title: str = ""):
        title = title or str(uuid4())
        new_ws = Document(name=title, type="Workspace", properties={"dc:title": title})
        ws = server.documents.create(new_ws, parent_path="/default-domain/workspaces")
        request.addfinalizer(ws.delete)
        log.debug(f"[FIXTURE] Created {ws}")

        # Convenient attributes
        for k, v in ws.properties.items():
            setattr(ws, k, v)

        return ws

    yield _make_workspace


@pytest.fixture(scope="session")
def set_acls(server):
    def set_readonly(user: str, doc_path: str, readonly: bool = True):
        """
        Mark a document as RO or RW.

        :param user: Affected username.
        :param doc_path: The document, either a folder or a file.
        :param readonly: Set RO if True else RW.
        """
        input_obj = f"doc:{doc_path}"
        if readonly:
            server.operations.execute(
                command="Document.SetACE",
                input_obj=input_obj,
                user=user,
                permission="Read",
                void_op=True,
            )
            block_inheritance(server, doc_path, overwrite=False)
        else:
            server.operations.execute(
                command="Document.SetACE",
                input_obj=input_obj,
                user=user,
                permission="ReadWrite",
                grant=True,
                void_op=True,
            )

    yield set_readonly


def block_inheritance(server: Nuxeo, ref: str, overwrite: bool = True):
    input_obj = f"doc:{ref}"

    server.operations.execute(
        command="Document.SetACE",
        input_obj=input_obj,
        user="Administrator",
        permission="Everything",
        overwrite=overwrite,
        void_op=True,
    )

    server.operations.execute(
        command="Document.SetACE",
        input_obj=input_obj,
        user="Everyone",
        permission="Everything",
        grant=False,
        overwrite=False,
        void_op=True,
    )
