import os.path
import shutil
import stat
import tempfile
from logging import getLogger

import pytest
from nuxeo.documents import Document

from nxdrive.constants import WINDOWS

from ... import env
from .utils import cb_get, fatal_error_dlg  # , get_opened_url

if not WINDOWS:
    pytestmark = pytest.mark.skip("Windows only.")

log = getLogger(__name__)


def launch(exe, args: str, wait: int = 0) -> None:
    try:
        with exe(args=args, wait=wait) as app:
            print(">>>>>>>>> in try block")
            return not fatal_error_dlg(app)
    except Exception as exc:
        print(f">>>>>>>>> in except block, {exc}")
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
    assert bind(exe, args.format(user=env.NXDRIVE_TEST_USERNAME, url=nuxeo_url))


@pytest.mark.parametrize(
    "args",
    [
        "",
        env.NXDRIVE_TEST_USERNAME,
        env.NXDRIVE_TEST_NUXEO_URL,
        f"--password={env.NXDRIVE_TEST_PASSWORD}",
        "--local-folder=foo",
    ],
)
def test_bind_server_missing_arguments(exe, args):
    assert not bind(exe, args)


@pytest.mark.parametrize("folder", ["Léa$", "this folder is good enough こん ツリ ^^"])
def test_unbind_server(nuxeo_url, exe, folder):
    """Will also test clean-folder."""
    folder = tempfile.TemporaryDirectory(prefix=folder)
    expanded_folder = folder.name
    local_folder = f'--local-folder "{expanded_folder}"'
    test_password = f"--password {env.NXDRIVE_TEST_PASSWORD}"
    args = f"{test_password} {local_folder} {env.NXDRIVE_TEST_USERNAME} {nuxeo_url}"

    try:
        assert bind(exe, args)
        assert os.path.isdir(expanded_folder)
        assert unbind(exe, local_folder)
    finally:
        assert launch(exe, f"clean-folder {local_folder}")

        os.chmod(expanded_folder, stat.S_IWUSR)
        shutil.rmtree(expanded_folder)
        folder.cleanup()
        assert not os.path.isdir(expanded_folder)


@pytest.mark.parametrize("folder", ["", "this folder does not exist こん ツリ ^^ Léa$"])
def test_unbind_server_missing_argument(exe, folder):
    """Without (or invalid) argument must not fail at all."""
    local_folder = f'--local-folder="{folder}"'
    assert unbind(exe, local_folder)


def test_bind_root_doc_not_found(nuxeo_url, exe, server, tmp):
    args = f"bind-root 'inexistant folder' --local-folder='{str(tmp())}'"
    assert not launch(exe, args)


def test_unbind_root_doc_not_found(nuxeo_url, exe, server, tmp):
    args = f"unbind-root 'inexistant folder' --local-folder='{str(tmp())}'"
    assert not launch(exe, args)


def test_complete_scenario_synchronization_from_zero(nuxeo_url, exe, server, tmp):
    """Automate things:
    - bind a server
    - bind a root
    - sync data
    - unbind the root
    - unbind the server
    """

    folder = tempfile.TemporaryDirectory(prefix="sync_test")
    expanded_folder = folder.name
    local_folder = f'--local-folder="{str(expanded_folder)}"'

    ws = None

    try:
        # 1st, bind the server
        args = f"{env.NXDRIVE_TEST_USERNAME} {nuxeo_url} {local_folder} --password {env.NXDRIVE_TEST_PASSWORD}"
        assert bind(exe, args)
        assert os.path.isdir(expanded_folder)

        # 2nd, create a workspace
        new = Document(
            name="sync and stop",
            type="Workspace",
            properties={"dc:title": "sync and stop"},
        )
        ws = server.documents.create(new, parent_path=env.WS_DIR)

        # 3rd, bind the root (e.g.: enable the sync of the workspace)
        print(f">>> ws.path: {ws.path}")
        args = f'bind-root "{ws.path}" {local_folder}'
        assert launch(exe, args, wait=5)

        # 4th, sync and quit
        assert launch(exe, "--sync-and-quit", wait=40)

        # Check
        print(f">> dir: {os.listdir(expanded_folder)}")
        new_path = os.path.join(expanded_folder, ws.title)
        assert os.path.isdir(new_path)

        # Unbind the root
        args = f'unbind-root "{ws.path}" {local_folder}'
        assert launch(exe, args)

        # Unbind the server
        assert unbind(exe, local_folder)
    finally:
        if ws:
            ws.delete()

        assert launch(exe, f"clean-folder {local_folder}")

        os.chmod(expanded_folder, stat.S_IWUSR)
        shutil.rmtree(expanded_folder)
        folder.cleanup()
        assert not os.path.isdir(expanded_folder)


def test_ctx_menu_access_online_inexistant(nuxeo_url, exe, server, tmp):
    """It should be a no-op, no fatal error."""
    args = 'access-online --file="bla bla bla"'
    assert launch(exe, args)


def test_ctx_menu_copy_share_link_inexistant(nuxeo_url, exe, server, tmp):
    args = 'copy-share-link --file="bla bla bla"'
    assert launch(exe, args)
    url_copied = cb_get()
    assert not url_copied.startswith(nuxeo_url)


def test_ctx_menu_edit_metadata_inexistant(nuxeo_url, exe, server, tmp):
    """It should be a no-op, no fatal error."""
    args = 'edit-metadata --file="bla bla bla"'
    assert launch(exe, args)


def test_ctx_menu_entries(nuxeo_url, exe, server, tmp):
    """Will test:
    - access-online
    - copy-share-link
    - edit-metadata
    """

    folder = tmp()
    assert not folder.is_dir()
    os.mkdir(folder)
    local_folder = f'--local-folder="{str(folder)}"'

    ws = None

    try:
        # 1st, bind the server
        args = f"{env.NXDRIVE_TEST_USERNAME} {nuxeo_url} {local_folder} --password {env.NXDRIVE_TEST_PASSWORD}"
        assert bind(exe, args)
        assert folder.is_dir()

        # 2nd, create a workspace
        new = Document(
            name="my workspace",
            type="Workspace",
            properties={"dc:title": "my workspace"},
        )
        ws = server.documents.create(new, parent_path=env.WS_DIR)

        # 3rd, bind the root (e.g.: enable the sync of the workspace)
        args = f'bind-root "{ws.path}" {local_folder}'
        assert launch(exe, args, wait=5)

        # 4th, sync and quit
        assert launch(exe, "--sync-and-quit", wait=40)

        # Check
        print(f">>> folder: {os.listdir(folder)}")
        synced_folder = os.path.join(folder, ws.title)
        print(f">>> cwd: {os.getcwd()}")

        os.mkdir(synced_folder)
        print(f">>> folder: {os.listdir(folder)}")
        assert os.path.isdir(synced_folder)

        # Get the copy-share link
        args = f'copy-share-link --file="{str(synced_folder)}"'
        assert launch(exe, args)
        url_copied = cb_get()
        assert url_copied.startswith(nuxeo_url)
        assert url_copied.endswith(ws.uid)

        # Test access-online, it should open a browser
        args = f'access-online --file="{str(synced_folder)}"'
        assert launch(exe, args)
        # assert get_opened_url() == url_copied

        # Test edit-metadata, it should open a browser
        args = f'edit-metadata --file="{str(synced_folder)}"'
        assert launch(exe, args)
        # assert get_opened_url() == url_copied
    finally:
        if ws:
            ws.delete()

        assert launch(exe, f"clean-folder {local_folder}")

        os.chmod(folder, stat.S_IWUSR)
        shutil.rmtree(folder)
        assert not os.path.isdir(folder)
