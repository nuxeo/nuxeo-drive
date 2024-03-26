from .common import OneUserTest


class TestEncoding(OneUserTest):
    def test_filename_with_accents_from_server(self):
        local = self.local_1
        remote = self.remote_document_client_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        data = b"Contenu sans accents."
        remote.make_file(self.workspace, "Nom sans accents.doc", content=data)
        remote.make_file(self.workspace, "Nom avec accents \xe9 \xe8.doc", content=data)
        self.wait_sync(wait_for_async=True)

        assert local.get_content("/Nom sans accents.doc") == data
        assert local.get_content("/Nom avec accents \xe9 \xe8.doc") == data

    def test_filename_with_katakana(self):
        local = self.local_1
        remote = self.remote_document_client_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        data = b"Content"
        remote.make_file(self.workspace, "Remote \u30bc\u30ec.doc", content=data)
        local.make_file("/", "Local \u30d7 \u793e.doc", content=data)
        self.wait_sync(wait_for_async=True)

        assert remote.get_content("/Local \u30d7 \u793e.doc") == data
        assert local.get_content("/Remote \u30bc\u30ec.doc") == data

    def test_content_with_accents_from_server(self):
        local = self.local_1
        remote = self.remote_document_client_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        data = "Contenu avec caract\xe8res accentu\xe9s.".encode("utf-8")
        remote.make_file(self.workspace, "Nom sans accents.txt", content=data)
        self.wait_sync(wait_for_async=True)

        assert local.get_content("/Nom sans accents.txt") == data

    def test_filename_with_accents_from_client(self):
        local = self.local_1
        remote = self.remote_document_client_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        data = b"Contenu sans accents."
        local.make_file("/", "Avec accents \xe9 \xe8.doc", content=data)
        local.make_file("/", "Sans accents.doc", content=data)
        self.wait_sync(wait_for_async=True)

        assert remote.get_content("/Avec accents \xe9 \xe8.doc") == data
        assert remote.get_content("/Sans accents.doc") == data

    def test_content_with_accents_from_client(self):
        local = self.local_1
        remote = self.remote_document_client_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        data = "Contenu avec caract\xe8res accentu\xe9s.".encode("utf-8")
        local.make_file("/", "Nom sans accents", content=data)
        self.wait_sync(wait_for_async=True)

        assert remote.get_content("/Nom sans accents") == data
