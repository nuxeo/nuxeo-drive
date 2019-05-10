# coding: utf-8
from logging import getLogger
from typing import Callable
from random import randint
from uuid import uuid4

import nuxeo
import nuxeo.client
import nuxeo.operations
import pytest
from faker import Faker
from nuxeo.client import Nuxeo
from nuxeo.documents import Document
from nuxeo.users import User

from nxdrive.manager import Manager


# Operations cache
OPS_CACHE = None
SERVER_INFO = None

log = getLogger(__name__)


@pytest.fixture(scope="session")
def server(nuxeo_url):
    """
    Get the Nuxeo instance.

    For now, we do not allow to use another than Administrator:Administrator
    to prevent unexpected actions on critical servers.
    """
    auth = ("Administrator", "Administrator")
    server = Nuxeo(host=nuxeo_url, auth=auth)
    server.client.set(schemas=["dublincore"])

    # Save bandwith by caching operations details
    global OPS_CACHE
    if not OPS_CACHE:
        OPS_CACHE = server.operations.operations
        nuxeo.operations.API.ops = OPS_CACHE
    global SERVER_INFO
    if not SERVER_INFO:
        SERVER_INFO = server.client.server_info()
        nuxeo.client.NuxeoClient._server_info = SERVER_INFO

    return server


@pytest.fixture(scope="session")
def faker() -> Callable[[], Faker]:
    """
    Get a Faker object to simplify other object creation.
    Note the using fr_FR will break tests when the username contains accent.
    """

    def _faker(l10n: str = "en_US") -> Faker:
        return Faker(l10n)

    return _faker


@pytest.fixture
def manager_factory(
    request, tmp, nuxeo_url, user_factory, server
) -> Callable[[], Manager]:
    """Manager instance with automatic clean-up."""

    def _make_manager(home: str = "", with_engine: bool = True):
        manager = Manager(home or tmp())

        # Force deletion behavior to real deletion for all tests
        manager._dao.update_config("deletion_behavior", "delete_server")
        manager._dao.store_bool("show_deletion_prompt", False)

        request.addfinalizer(manager.close)
        log.info(f"[FIXTURE] Created {manager}")

        if with_engine:
            conf_folder = manager.home / "nuxeo-conf"
            user = user_factory()
            manager.bind_server(
                conf_folder, nuxeo_url, user.uid, user.password, start_engine=False
            )

            engine = None
            for uid, engine_ in manager.get_engines().items():
                engine = engine_

            return manager, engine

        return manager

    yield _make_manager


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
        username = f"{first_name.lower()}-{randint(1, 99_999)}"
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
        log.info(f"[FIXTURE] Created {user}")

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
        log.info(f"[FIXTURE] Created {ws}")

        # Convenient attributes
        for k, v in ws.properties.items():
            setattr(ws, k, v)

        return ws

    yield _make_workspace
