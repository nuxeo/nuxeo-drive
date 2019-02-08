# coding: utf-8
import os
from contextlib import suppress
from logging import getLogger
from pathlib import Path
from shutil import rmtree

import pytest
from faker import Faker
from nuxeo.client import Nuxeo
from nuxeo.users import User

from nxdrive.manager import Manager


DEFAULT_NUXEO_URL = "http://localhost:8080/nuxeo"
log = getLogger(__name__)


@pytest.fixture(scope="session")
def faker():
    def _faker(l10n: str = "fr_FR"):
        log.debug(f"[FIXTURE] Using Faker with {l10n} localization")
        return Faker(l10n)

    return _faker


@pytest.fixture(scope="session")
def nuxeo_url():
    url = os.getenv("NXDRIVE_TEST_NUXEO_URL", DEFAULT_NUXEO_URL)
    url = url.split("#")[0]
    log.debug(f"[FIXTURE] Nuxeo URL is {url!r}")
    return url


@pytest.fixture(scope="session")
def version():
    import nxdrive

    return nxdrive.__version__


@pytest.fixture
def tempdir(tmpdir):
    path = Path(tmpdir)
    try:
        yield path
    finally:
        with suppress(OSError):
            rmtree(path)


@pytest.fixture
def manager(tempdir):
    with Manager(home=tempdir) as man:
        yield man


@pytest.fixture(scope="module")
def server(nuxeo_url):
    server = Nuxeo(host=nuxeo_url, auth=("Administrator", "Administrator"))
    server.client.set(schemas=["dublincore"])
    return server


@pytest.fixture
def user_factory(server, faker):

    _user = None
    fake = faker()

    def _create_user(
        password: str = "Administrator",
        lastName: str = fake.last_name(),
        firstName: str = fake.first_name(),
        email: str = fake.email(),
        company: str = fake.company(),
    ):
        nonlocal _user

        username: str = firstName.lower()
        user_ = User(
            properties={
                "lastName": lastName,
                "firstName": firstName,
                "username": username,
                "email": email,
                "company": company,
                "password": password,
            }
        )
        _user = server.users.create(user_)
        _user.password = password
        log.debug(f"[FIXTURE] Created user {user_}")
        return _user

    try:
        yield _create_user
    finally:
        with suppress(Exception):
            _user.delete()
