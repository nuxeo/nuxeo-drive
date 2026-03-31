"""
Migration to add the DirectDownloads table for tracking direct download operations.
"""
from sqlite3 import Cursor

from ..migration import MigrationInterface


class MigrationDirectDownloads(MigrationInterface):
    """Migration to create the DirectDownloads table."""

    def upgrade(self, cursor: Cursor) -> None:
        """
        Create the DirectDownloads table.
        """
        self._create_direct_downloads_table(cursor)

    def downgrade(self, cursor: Cursor) -> None:
        """
        Drop the DirectDownloads table.
        """
        cursor.execute("DROP TABLE IF EXISTS DirectDownloads")

    @property
    def version(self) -> int:
        return 23

    @property
    def previous_version(self) -> int:
        return 22

    @staticmethod
    def _create_direct_downloads_table(cursor: Cursor) -> None:
        """Create the DirectDownloads table."""
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS DirectDownloads ("
            "    uid                INTEGER     PRIMARY KEY,"
            "    doc_uid            VARCHAR     NOT NULL,"
            "    doc_name           VARCHAR     NOT NULL,"
            "    doc_size           INTEGER     DEFAULT 0,"
            "    download_path      VARCHAR,"
            "    server_url         VARCHAR     NOT NULL,"
            "    status             INTEGER     DEFAULT 0,"
            "    bytes_downloaded   INTEGER     DEFAULT 0,"
            "    total_bytes        INTEGER     DEFAULT 0,"
            "    progress_percent   REAL        DEFAULT 0.0,"
            "    created_at         TIMESTAMP   NOT NULL    DEFAULT CURRENT_TIMESTAMP,"
            "    started_at         TIMESTAMP,"
            "    completed_at       TIMESTAMP,"
            "    is_folder          INTEGER     DEFAULT 0,"
            "    folder_count       INTEGER     DEFAULT 0,"
            "    file_count         INTEGER     DEFAULT 1,"
            "    retry_count        INTEGER     DEFAULT 0,"
            "    last_error         VARCHAR,"
            "    engine             VARCHAR     DEFAULT '',"
            "    zip_file           VARCHAR,"
            "    selected_items     VARCHAR"
            ")"
        )


migration = MigrationDirectDownloads()
