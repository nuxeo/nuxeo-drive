import os.path
import shutil
import stat
from logging import getLogger

import pytest

from .utils import fatal_error_dlg


log = getLogger(__name__)


def launch(exe, args: str) -> None:
    try:
        with exe(args=args) as app:
            return not fatal_error_dlg(app)
    except Exception:
        return False


def bind(exe, args: str) -> None:
    """bind-server option. Used at several places so moved out test functions."""
    return launch(exe, f"bind-server {args}")


def unbind(exe, args: str) -> None:
    """unbind-server option. Used at several places so moved out test functions."""
    return launch(exe, f"unbind-server {args}")


def test_console(exe):
    assert launch(exe, "console")


@pytest.mark.parametrize(
    "args",
    [
        "{user} {url}",
        "{user} {url} --password=BadP@ssw0rd",
        # --local-folder argument is tested in test_unbind()
    ],
)
def test_bind_server(nuxeo_url, exe, args):
    """
    Test only with no access to the server to prevent useless binds.
    Real binds are tested in test_unbind_server().
    """
    assert bind(exe, args.format(user="Administrator", url=nuxeo_url))


@pytest.mark.parametrize(
    "args",
    [
        "",
        "Administrator",
        "http://localhost:8080/nuxeo",
        "--password=Administrator",
        "--local-folder=foo",
    ],
)
def test_bind_server_missing_arguments(exe, args):
    assert not bind(exe, args)


@pytest.mark.parametrize(
    "folder", ["%temp%\\Léa$", "%temp%\\this folder is good enough こん ツリ ^^"]
)
def test_unbind_server(nuxeo_url, exe, folder):
    """Will also test clean-folder."""
    expanded_folder = os.path.expandvars(folder)
    local_folder = f'--local-folder="{folder}"'
    args = f"Administrator {nuxeo_url} {local_folder}"

    try:
        assert bind(exe, args)
        assert os.path.isdir(expanded_folder)
        assert unbind(exe, local_folder)
    finally:
        assert launch(exe, f"clean-folder {local_folder}")

        os.chmod(expanded_folder, stat.S_IWUSR)
        shutil.rmtree(expanded_folder)
        assert not os.path.isdir(expanded_folder)


@pytest.mark.parametrize("folder", ["", "this folder does not exist こん ツリ ^^ Léa$"])
def test_unbind_server_missing_argument(exe, folder):
    """Without (or invalid) argument must not fail at all."""
    local_folder = f'--local-folder="{folder}"'
    assert unbind(exe, local_folder)
