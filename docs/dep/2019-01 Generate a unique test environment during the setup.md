# Generate a unique test environment during the setup

- Created: 2019-01-31
- Last-Modified: 2019-05-17
- Author: Mickaël Schoentgen <mschoentgen@nuxeo.com>,
          Léa Klein <lklein@nuxeo.com>
- Status: implemented
- Related-Ticket: [NXDRIVE-1436](https://jira.nuxeo.com/browse/NXDRIVE-1436)
                  [NXDRIVE-1542](https://jira.nuxeo.com/browse/NXDRIVE-1542)

## Abstract

Generate a test environment that will be unique to the run time.
Running the test suite twice should not use same users and workspaces to ensure tests reproducibility, reliability and debugging.

## Rationale

As of now, tests are calling the `NuxeoDrive.SetupIntegrationTests` operation to create users and workspaces.

With the future move to Jenkins X for testing ([NXDRIVE-1435](https://jira.nuxeo.com/browse/NXDRIVE-1435)), we will encounter errors because 3 OSes will talk to the server at the same time.
It will break everything as users and workspaces are the same everywhere.

Before that move, we need to tweak tests setup to:

- create needed user for each tests;
- create the workspace based on the OS name and the test name/function/whatever (we should keep it short for OS path limits);
- enable synchronization of that workspace for users that need it;
- clean-up everything at the end of the test.

### Idea

Using the Python client, we should be able to create what we need.
We shouldn't call the `NuxeoDrive.SetupIntegrationTests` operation anymore.

## Specifications

We will completely move to `pytest` instead of having a mix with `unittest` format.
We will then be able to fully embrace pytest [fixture's factories](https://docs.pytest.org/en/latest/fixture.html#factories-as-fixtures).
Speaking of factories, we may have a look at [Factory Boy](https://factoryboy.readthedocs.io/en/latest/).

We will split the `tests` folder to reflect the actual test files it contains.
I am thinking of something like:

```text
tests/
    - conftest.py (global fixtures)
    - /functional
        - conftest.py (Nuxeo server specific fixtures)
        - test_local_creations.py
        - test_synchronization.py
    - /integration (for the future)
    - /unit
        - conftest.py (fixtures needed locally)
        - test_report.py
        - tet_utils.py
```

Where:

- `tests/functional` are tests that require a Nuxeo instance to work with.
- `test/integration` will be the folder where real scenarii will be tested.
- `test/unit` are real unit tests, with no requirements but the Nuxeo Drive code.

It will speed tests because only `tests/functional` will require a server connection and it will help future parallelization.

## Examples

Converting `test_bind_server.py` to the proposed new format will convert this code:

```python
import os
import tempfile
import unittest
from pathlib import Path

import pytest

from nxdrive.exceptions import FolderAlreadyUsed
from nxdrive.manager import Manager
from nxdrive.options import Options
from nxdrive.utils import normalized_path
from .common import TEST_DEFAULT_DELAY, clean_dir


class BindServerTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(os.environ.get("WORKSPACE", "")) / "tmp"
        self.addCleanup(clean_dir, self.tmpdir)
        self.tmpdir.mkdir(parents=True, exist_ok=True)

        self.local_test_folder = normalized_path(
            tempfile.mkdtemp("-nxdrive-temp-config", dir=self.tmpdir)
        )
        self.nxdrive_conf_folder = self.local_test_folder / "nuxeo-drive-conf"

    def tearDown(self):
        Manager._singleton = None

    @Options.mock()
    def test_bind_local_folder_on_config_folder(self):
        Options.delay = TEST_DEFAULT_DELAY
        Options.nxdrive_home = self.nxdrive_conf_folder
        self.manager = Manager()

        with pytest.raises(FolderAlreadyUsed):
            self.manager.bind_server(
                self.nxdrive_conf_folder,
                pytest.nuxeo_url,
                pytest.user,
                pytest.password,
                start_engine=False,
            )
            self.addCleanup(self.manager.unbind_all)
            self.addCleanup(self.manager.dispose_all)

```

To this one, more concise and readable:

```python
import pytest

from nxdrive.exceptions import FolderAlreadyUsed


def test_bind_local_folder_already_used(manager, tempdir, nuxeo_url, user_factory):
    conf_folder = tempdir / "nuxeo-conf"
    user = user_factory()

    # First bind: OK
    manager.bind_server(
        conf_folder, nuxeo_url, user.uid, user.password, start_engine=False
    )

    # Second bind: Error
    with pytest.raises(FolderAlreadyUsed):
        manager.bind_server(
            conf_folder, nuxeo_url, user.uid, user.password, start_engine=False
        )
```

We defined several fixtures: `manager`, `tempdir`, `nuxeo_url` and `user_factory`.

And they are defined as:

```python
@pytest.fixture(scope="session")
def nuxeo_url():
    """Retrieve the Nuxeo URL."""
    return os.getenv("NXDRIVE_TEST_NUXEO_URL", "http://localhost:8080/nuxeo").split("#")[0]


@pytest.fixture()
def tempdir(tmpdir):
    """Use the original *tmpdir* fixture and convert to a Path with automatic clean-up."""
    path = Path(tmpdir)
    try:
        yield path
    finally:
        with suppress(OSError):
            rmtree(path)


@pytest.fixture()
def manager(tempdir):
    """Manager instance with automatic clean-up."""
    with Manager(tempdir) as man:
        yield man


@pytest.fixture()
def user_factory(server, faker):
    """User creation factory with automatic clean-up."""
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
                'lastName': lastName,
                'firstName': firstName,
                'username': username,
                'email': email,
                'company': company,
                'password': password,
            },
        )
        _user = server.users.create(user_)
        _user.password = password
        return _user

    try:
        yield _create_user
    finally:
        with suppress(Exception):
            _user.delete()
```

This may look like a lot of code, but it is a small addition compared to what we'll be able to factorized across all tests.
