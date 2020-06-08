# coding: utf-8
from logging import getLogger
from pathlib import Path
from random import randint
from typing import Callable, Optional
from uuid import uuid4

import pytest
from faker import Faker
from nuxeo.documents import Document
from nuxeo.users import User
from nxdrive.manager import Manager

from .. import env

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


@pytest.fixture()
def manager_factory(
    request, tmp, nuxeo_url, user_factory, server
) -> Callable[[], Manager]:
    """Manager instance with automatic clean-up."""

    def _make_manager(
        home: str = "",
        with_engine: bool = True,
        local_folder: Optional[Path] = None,
        user: Optional[User] = None,
    ):
        manager = Manager(home or tmp())

        # Force deletion behavior to real deletion for all tests
        manager.dao.update_config("deletion_behavior", "delete_server")
        manager.dao.store_bool("show_deletion_prompt", False)

        request.addfinalizer(manager.close)
        log.info(f"[FIXTURE] Created {manager}")

        if with_engine:
            conf_folder = (local_folder or manager.home) / "nuxeo-conf"
            user = user or user_factory()
            manager.bind_server(
                conf_folder, nuxeo_url, user.uid, user.password, start_engine=False
            )

            # Let the possibility to access user's attributes from the manager
            manager.user_details = user

            engine = None
            for engine_ in manager.engines.values():
                engine = engine_

            return manager, engine

        return manager

    yield _make_manager


@pytest.fixture()
def user_factory(request, server, faker):
    """User creation factory with automatic clean-up."""

    fake = faker()
    company = fake.company()
    company_domain = (
        company.lower().replace(",", "_").replace(" ", "_").replace("-", "_")
    )

    def _make_user(username: str = "", password: str = "Administrator"):
        first_name, last_name = fake.name().split(" ", 1)
        username = username or f"{first_name.lower()}-{randint(1, 99_999)}"
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


@pytest.fixture()
def obj_factory(request, server):
    """File/Folder/Workspace creation factory with automatic clean-up."""

    def _make(
        title: str = "",
        nature: str = "Folder",
        parent: str = env.WS_DIR,
        enable_sync: bool = False,
    ):
        title = title or str(uuid4())
        new = Document(name=title, type=nature, properties={"dc:title": title})
        obj = server.documents.create(new, parent_path=env.WS_DIR)
        request.addfinalizer(obj.delete)
        log.info(f"[FIXTURE] Created {obj}")

        # Convenient attributes
        for k, v in obj.properties.items():
            setattr(obj, k, v)

        if enable_sync:
            operation = server.operations.new("NuxeoDrive.SetSynchronization")
            operation.params = {"enable": True}
            operation.input_obj = obj.path
            operation.execute()

        return obj

    yield _make
