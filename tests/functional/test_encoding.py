import os
from pathlib import Path

from nxdrive.client.local import FileInfo

from ..markers import not_mac
from .conftest import OneUserTest


class TestEncoding(OneUserTest):
    def test_name_normalization(self):
        local = self.local_1
        remote = self.remote_document_client_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        filename = "space\xa0 et TM\u2122.doc"
        local.make_file("/", filename)
        self.wait_sync(wait_for_async=True)

        assert remote.get_info("/" + filename).name == filename

    @not_mac(reason="Normalization does not work on macOS")
    def test_fileinfo_normalization(self):
        local = self.local_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.engine_1.stop()

        name = "Teste\u0301"
        local.make_file("/", name, content=b"Test")

        # FileInfo() will normalize the filename
        assert FileInfo(local.base_folder, Path(name), False, 0).name != name

        # The encoding should be different,
        # cannot trust the get_children as they use FileInfo
        children = os.listdir(local.abspath("/"))
        assert len(children) == 1
        assert children[0] != name
