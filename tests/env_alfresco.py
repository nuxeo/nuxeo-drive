"""Environment constants for Alfresco Drive test runs.

Everything here is driven by environment variables so credentials are
never checked into source control. In CI (see
``.github/workflows/*_alfresco.yml``) they are injected from repository
secrets; for local runs, export them in your shell before invoking
``tox`` / ``pytest``:

.. code-block:: shell

    export ALFRESCO_URL="https://your-alfresco.example.com"
    export ALFRESCO_USER="<username>"
    export ALFRESCO_PASSWORD="<secret>"
"""

from os import getenv

# The Alfresco server URL against which to run tests.
# When empty, functional / integration tests are skipped by the
# ``tests/alfresco/conftest.py`` guard.
ALFRESCO_URL = getenv("ALFRESCO_URL", "")

# The user having administrator rights on the Alfresco server.
ALFRESCO_USER = getenv("ALFRESCO_USER", "")

# The password associated with ``ALFRESCO_USER``.
ALFRESCO_PASSWORD = getenv("ALFRESCO_PASSWORD", "")

# Optional OAuth2 client id / secret used when exercising the AIMS
# discovery flow (``nxdrive.alfresco.auth.oauth2``). Populate only if
# your Alfresco deployment has an ADW / AIMS realm configured.
ALFRESCO_OAUTH_CLIENT_ID = getenv("ALFRESCO_OAUTH_CLIENT_ID", "")
ALFRESCO_OAUTH_CLIENT_SECRET = getenv("ALFRESCO_OAUTH_CLIENT_SECRET", "")

# The remote root path where test content is created. Alfresco browses
# its content tree under ``/Company Home``; a dedicated ``Drive Tests``
# folder is preferred so ``tests/alfresco/cleanup.py`` can wipe it
# without touching unrelated content.
ALFRESCO_TEST_PATH = getenv("ALFRESCO_TEST_PATH", "/Company Home/Drive Tests")

# On Windows, this is used to define the drive letter of a second NTFS
# partition. Same knob as for Nuxeo tests.
SECOND_PARTITION = getenv("SECOND_PARTITION", "Q:\\")

# Alfresco doesn't expose "document types" the way Nuxeo does — content
# is modeled by a fixed ``cm:content`` / ``cm:folder`` pair. These are
# retained for symmetry with :mod:`tests.env_nuxeo` and consumed by
# any test that needs a stand-in doc-type constant.
DOCTYPE_FILE = getenv("ALFRESCO_DOCTYPE_FILE", "cm:content")
DOCTYPE_FOLDERISH = getenv("ALFRESCO_DOCTYPE_FOLDERISH", "cm:folder")
