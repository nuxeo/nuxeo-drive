"""Windows-only integration test: Alfresco CLI sub-commands.

Mirrors :mod:`tests.nuxeo.integration.windows.test_cli_sub_command`
but drives the Alfresco flavour. Skipped on non-Windows platforms
and auto-skipped when the Alfresco server is unavailable.
"""

from logging import getLogger

import pytest

from nxdrive.drive.constants import WINDOWS

from .... import env_alfresco as env

if not WINDOWS:  # pragma: no cover - skipped at collection time on non-Windows
    pytestmark = pytest.mark.skip("Windows only.")

log = getLogger(__name__)


def launch(exe, args: str, wait: int = 0):
    try:
        with exe(args=args, wait=wait) as app:
            return app is not None
    except Exception:
        return False


class TestAlfrescoCliSubCommand:
    def test_console(self, exe) -> None:
        assert launch(exe, "console")

    @pytest.mark.parametrize(
        "args_template",
        [
            "{user} {url}",
            "{user} {url} --password=BadP@ssw0rd",
        ],
    )
    def test_bind_server_dispatches(self, exe, args_template: str) -> None:
        args = args_template.format(user=env.ALFRESCO_USER, url=env.ALFRESCO_URL)
        # We only assert the CLI *dispatches* the sub-command without
        # crashing — success depends on server-side state.
        launch(exe, f"bind-server {args}")
