import hashlib
import os
from pathlib import Path
from time import sleep

import pytest

from nxdrive.client.local import LocalClient
from nxdrive.constants import ROOT, WINDOWS
from nxdrive.exceptions import DuplicationDisabledError, NotFound

EMPTY_DIGEST = hashlib.md5().hexdigest()
SOME_TEXT_CONTENT = b"Some text content."
SOME_TEXT_DIGEST = hashlib.md5(SOME_TEXT_CONTENT).hexdigest()


class MockedLocalClient(LocalClient):
    def make_file(self, parent: Path, name: str, content: bytes = None) -> Path:
        file = self.get_new_file(parent, name)[1]
        if content:
            file.write_bytes(content)
        else:
            file.touch()
        return file


@pytest.fixture
def local(tmp_path):
    yield MockedLocalClient(tmp_path)


@pytest.mark.timeout(30)
def test_case_sensitivity(local):
    sensitive = local.is_case_sensitive()

    local.make_file(ROOT, "abc.txt")
    if sensitive:
        local.make_file(ROOT, "ABC.txt")
    else:
        with pytest.raises(DuplicationDisabledError):
            local.make_file(ROOT, "ABC.txt")
    assert len(local.get_children_info(ROOT)) == sensitive + 1


@pytest.mark.xfail(
    WINDOWS,
    raises=OSError,
    reason="Explorer cannot find the directory as the path is way to long",
)
def test_complex_filenames(local):
    # Create another folder with the same title
    title_with_accents = "\xc7a c'est l'\xe9t\xe9 !"

    folder_1 = local.make_folder(ROOT, title_with_accents)
    folder_1_info = local.get_info(folder_1)
    assert folder_1_info.name == title_with_accents

    # Create another folder with the same title
    with pytest.raises(DuplicationDisabledError):
        local.make_folder(ROOT, title_with_accents)

    # Create a long file name with weird chars
    long_filename = "\xe9" * 50 + "%$#!()[]{}+_-=';&^.doc"
    file_1 = local.make_file(folder_1, long_filename)
    file_1_info = local.get_info(Path(folder_1) / file_1.name)
    assert file_1_info.name == long_filename
    assert file_1_info.path == folder_1_info.path / long_filename

    # Create a file with invalid chars
    invalid_filename = 'a/b\\c*d:e<f>g?h"i|j.doc'
    escaped_filename = "a-b-c-d-e-f-g-h-i-j.doc"
    file_2 = local.make_file(folder_1, invalid_filename)
    file_2_info = local.get_info(Path(folder_1) / file_2.name)
    assert file_2_info.name == escaped_filename
    assert file_2_info.path == folder_1_info.path / escaped_filename


@pytest.mark.xfail(
    WINDOWS, raises=OSError, reason="Explorer cannot deal with very long paths"
)
def test_deep_folders(local):
    """Check the LocalClient can workaround the default Windows MAX_PATH limit."""
    folder = ROOT
    for _i in range(30):
        folder = local.make_folder(folder, "0123456789")

    # Last Level
    last_level_folder_info = local.get_info(folder)
    assert last_level_folder_info.path == Path("0123456789/" * 30)

    # Create a nested file
    deep_file = local.make_file(folder, "File.txt", content=b"Some Content.")
    deep_file = local.get_path(deep_file)

    # Check the consistency of get_children_info and get_info
    deep_file_info = local.get_info(deep_file)
    deep_children = local.get_children_info(folder)
    assert len(deep_children) == 1
    deep_child_info = deep_children[0]
    assert deep_file_info.name == deep_child_info.name
    assert deep_file_info.path == deep_child_info.path
    assert deep_file_info.get_digest() == deep_child_info.get_digest()

    # Update the file content
    local.abspath(deep_file).write_bytes(b"New Content.")

    # Delete the folder
    local.delete(folder)
    assert not local.exists(folder)
    assert not local.exists(deep_file)

    # Delete the root folder and descendants
    local.delete("/0123456789")
    assert not local.exists("/0123456789")


def test_get_children_info(local):
    folder_1 = local.make_folder(ROOT, "Folder 1")
    folder_2 = local.make_folder(ROOT, "Folder 2")
    file_1 = local.make_file(ROOT, "File 1.txt", content=b"foo\n")

    # Not a direct child of '/'
    local.make_file(ROOT / folder_1.name, "File 2.txt", content=b"bar\n")

    # Ignored files
    data = b"baz\n"
    ignored_files = [
        ".File 2.txt",
        "~$File 2.txt",
        "File 2.txt~",
        "File 2.txt.swp",
        "File 2.txt.lock",
        "File 2.txt.part",
    ]
    for file in ignored_files:
        local.make_file(ROOT, file, content=data)
    if local.is_case_sensitive():
        local.make_file(ROOT, "File 2.txt.LOCK", content=data)
    else:
        with pytest.raises(DuplicationDisabledError):
            local.make_file(ROOT, "File 2.txt.LOCK", content=data)

    workspace_children = local.get_children_info(ROOT)
    assert len(workspace_children) == 3
    assert workspace_children[0].path == local.get_path(file_1)
    assert workspace_children[1].path == folder_1
    assert workspace_children[2].path == folder_2


def test_get_info_invalid_date(local):
    doc_1 = local.make_file(ROOT, "Document 1.txt")
    os.utime(local.abspath("Document 1.txt"), (0, 999999999999999))
    doc_1_info = local.get_info(doc_1)
    assert doc_1_info.name == "Document 1.txt"
    assert doc_1_info.path == doc_1
    assert doc_1_info.get_digest() == EMPTY_DIGEST
    assert not doc_1_info.folderish


def test_get_new_file(local):
    path, os_path, name = local.get_new_file(ROOT, "Document 1.txt")
    assert path == Path("Document 1.txt")
    assert str(os_path).endswith("Document 1.txt")
    assert name == "Document 1.txt"
    assert not local.exists(path)
    assert not os_path.exists()


def test_get_path(local):
    path = local.base_folder / "foo.txt"
    path_upper = local.base_folder / "FOO.TXT"

    # The path does not exist, it returns ROOT
    assert local.get_path(Path("été.doc")) == ROOT

    # The path exists, it returns
    assert local.get_path(path) == Path("foo.txt")
    assert local.get_path(path_upper) == Path("FOO.TXT")


def test_is_equal_digests(local):
    content = b"joe"
    local_path = local.make_file(ROOT, "File.txt", content=content)
    local_digest = hashlib.md5(content).hexdigest()
    # Equal digests
    assert local.is_equal_digests(local_digest, local_digest, local_path)

    # Different digests with same digest algorithm
    other_content = b"jack"
    remote_digest = hashlib.md5(other_content).hexdigest()
    assert local_digest != remote_digest
    assert not local.is_equal_digests(local_digest, remote_digest, local_path)

    # Different digests with different digest algorithms but same content
    remote_digest = hashlib.sha1(content).hexdigest()
    assert local_digest != remote_digest
    assert local.is_equal_digests(local_digest, remote_digest, local_path)

    # Different digests with different digest algorithms and different
    # content
    remote_digest = hashlib.sha1(other_content).hexdigest()
    assert local_digest != remote_digest
    assert not local.is_equal_digests(local_digest, remote_digest, local_path)


def test_make_documents(local):
    doc_1 = local.make_file(ROOT, "Document 1.txt")
    assert local.exists(doc_1)
    doc_1_info = local.get_info(doc_1)
    assert doc_1_info.name == "Document 1.txt"
    assert doc_1_info.path == doc_1
    assert doc_1_info.get_digest() == EMPTY_DIGEST
    assert not doc_1_info.folderish
    assert doc_1_info.size == 0

    doc_2 = local.make_file(ROOT, "Document 2.txt", content=SOME_TEXT_CONTENT)
    assert local.exists(doc_2)
    doc_2_info = local.get_info(doc_2)
    assert doc_2_info.name == "Document 2.txt"
    assert doc_2_info.path == doc_2
    assert doc_2_info.get_digest() == SOME_TEXT_DIGEST
    assert not doc_2_info.folderish
    assert doc_2_info.size > 0

    local.delete(doc_2)
    assert local.exists(doc_1)
    assert not local.exists(doc_2)

    folder_1 = local.make_folder(ROOT, "A new folder")
    assert local.exists(folder_1)
    folder_1_info = local.get_info(folder_1)
    assert folder_1_info.name == "A new folder"
    assert folder_1_info.path == folder_1
    assert folder_1_info.folderish
    # A folder has no size
    assert folder_1_info.size == 0

    doc_3 = local.make_file(
        ROOT / folder_1.name, "Document 3.txt", content=SOME_TEXT_CONTENT
    )
    local.delete(folder_1)
    assert not local.exists(folder_1)
    assert not local.exists(doc_3)


def test_missing_file(local):
    with pytest.raises(NotFound):
        local.get_info("/Something Missing")


def test_xattr_crud(local):
    """CRUD tests."""
    file = local.make_file(ROOT, "File 1.txt", content=b"baz\n")
    ref = file.name

    # Create
    local.set_remote_id(ref, "𝖀𝖓𝖎𝖈𝖔𝖉𝖊")
    local.set_remote_id(ref, "TEST", name="foo")

    # Read
    local.get_remote_id(ref) == "𝖀𝖓𝖎𝖈𝖔𝖉𝖊"
    local.get_remote_id(ref, name="foo") == "TEST"
    local.get_remote_id(ref, name="inexistent") == ""

    # Update
    local.set_remote_id(ref, "𝖀𝖓𝖎𝖈𝖔𝖉𝖊 with Space")
    local.set_remote_id(ref, "TEST2", name="foo")
    local.get_remote_id(ref) == "𝖀𝖓𝖎𝖈𝖔𝖉𝖊 with Space"
    local.get_remote_id(ref, name="foo") == "TEST2"

    # Delete
    local.remove_remote_id(ref)
    local.remove_remote_id(ref, name="foo")
    local.remove_remote_id(ref, name="inexistent")
    local.get_remote_id(ref) == ""
    local.get_remote_id(ref, name="foo") == ""


def test_xattr_error_invalid_start_byte(local):
    """Ensure this will never happen again:
    UnicodeDecodeError: 'utf-8' codec can't decode byte 0x80 in position 8: invalid start byte
    """
    file = local.make_file(ROOT, "test-xattr.txt", content=b"bla" * 3)
    raw_value, result_needed = b"fdrpMACS\x80", "fdrpMACS"
    local.set_path_remote_id(file, raw_value)
    assert local.get_path_remote_id(file) == result_needed


def test_xattr_mtime(local):
    """Ensure that playing with xattr does not change the file mtime."""
    file = local.make_file(ROOT, "File 2.txt", content=b"baz\n")
    ref = file.name
    path = local.abspath(ref)
    mtime = int(path.stat().st_mtime)
    sleep(1)
    local.set_remote_id(ref, "TEST")
    assert mtime == int(path.stat().st_mtime)
    sleep(1)
    local.remove_remote_id(ref)
    assert mtime == int(path.stat().st_mtime)
