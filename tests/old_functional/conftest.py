# coding: utf-8
import os

import nxdrive

from . import DocRemote


def pytest_namespace():
    """
    This namespace is used to store global variables for
    tests. They can be accessed with `pytest.<variable_name>`
    e.g. `pytest.nuxeo_url`
    """

    nuxeo_url = os.getenv(
        "NXDRIVE_TEST_NUXEO_URL", "http://localhost:8080/nuxeo"
    ).split("#")[0]
    password = os.getenv("NXDRIVE_TEST_PASSWORD", "Administrator")
    user = os.getenv("NXDRIVE_TEST_USER", "Administrator")
    version = nxdrive.__version__

    try:
        root_remote = DocRemote(
            nuxeo_url,
            user,
            "nxdrive-test-administrator-device",
            version,
            password=password,
            base_folder="/",
            timeout=60,
        )
    except:
        # When testing locally a function that does not need to communicate with the
        # server we can skip this object. To be reviewed with the tests refactoring.
        root_remote = None

    return {
        "nuxeo_url": nuxeo_url,
        "user": user,
        "password": password,
        "root_remote": root_remote,
        "version": version,
    }
