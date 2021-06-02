from sqlite3 import Cursor

from ..migration import MigrationInterface


class MigrationInitial(MigrationInterface):
    def upgrade(self, cursor: Cursor) -> None:
        """
        Create all the basics table.
        Setup the *journal_mode* and *temp_store*.
        """
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA temp_store = MEMORY")

        self._create_configuration_table(cursor)
        for table in ["Filters", "RemoteScan", "ToRemoteScan"]:
            cursor.execute(
                f"CREATE TABLE {table} ("
                "   path STRING NOT NULL,"
                "   PRIMARY KEY (path)"
                ")"
            )
        self._create_state_table(cursor)
        self._create_transfer_tables(cursor)
        self._create_sessions_table(cursor)
        self._create_session_items_table(cursor)

        cursor.execute(f"PRAGMA user_version = {self.version}")

    def downgrade(self, cursor: Cursor) -> None:
        """
        Drop all the created tables.
        Only revert the *user_version* PRAGMA.
        """
        for table in [
            "Configuration",
            "Filters",
            "RemoteScan",
            "ToRemoteScan",
            "States",
            "Downloads",
            "Uploads",
            "Sessions",
            "SessionItems",
        ]:
            cursor.execute(f"DROP TABLE {table}")

        cursor.execute(f"PRAGMA user_version = {self.previous_version}")

    @property
    def version(self) -> int:
        return 21

    @property
    def previous_version(self) -> int:
        return 0

    def _create_configuration_table(self, cursor: Cursor, /) -> None:
        """Create the Configuration table."""
        cursor.execute(
            "CREATE TABLE Configuration ("
            "    name    VARCHAR NOT NULL,"
            "    value   VARCHAR,"
            "    PRIMARY KEY (name)"
            ")"
        )

    @staticmethod
    def _create_state_table(cursor: Cursor) -> None:
        """Create the States table."""
        # Cannot force UNIQUE for a local_path as a duplicate can have
        # virtually the same path until they are resolved by Processor
        # Should improve that
        cursor.execute(
            "CREATE TABLE States ("
            "    id                      INTEGER    NOT NULL,"
            "    last_local_updated      TIMESTAMP,"
            "    last_remote_updated     TIMESTAMP,"
            "    local_digest            VARCHAR,"
            "    remote_digest           VARCHAR,"
            "    local_path              VARCHAR,"
            "    remote_ref              VARCHAR,"
            "    local_parent_path       VARCHAR,"
            "    remote_parent_ref       VARCHAR,"
            "    remote_parent_path      VARCHAR,"
            "    local_name              VARCHAR,"
            "    remote_name             VARCHAR,"
            "    size                    INTEGER    DEFAULT (0),"
            "    folderish               INTEGER,"
            "    local_state             VARCHAR    DEFAULT('unknown'),"
            "    remote_state            VARCHAR    DEFAULT('unknown'),"
            "    pair_state              VARCHAR    DEFAULT('unknown'),"
            "    remote_can_rename       INTEGER,"
            "    remote_can_delete       INTEGER,"
            "    remote_can_update       INTEGER,"
            "    remote_can_create_child INTEGER,"
            "    last_remote_modifier    VARCHAR,"
            "    last_sync_date          TIMESTAMP,"
            "    error_count             INTEGER    DEFAULT (0),"
            "    last_sync_error_date    TIMESTAMP,"
            "    last_error              VARCHAR,"
            "    last_error_details      TEXT,"
            "    version                 INTEGER    DEFAULT (0),"
            "    processor               INTEGER    DEFAULT (0),"
            "    last_transfer           VARCHAR,"
            "    creation_date           TIMESTAMP,"
            "    duplicate_behavior      VARCHAR    DEFAULT ('create'),"
            "    session                 INTEGER    DEFAULT (0),"
            "    PRIMARY KEY (id),"
            "    UNIQUE(remote_ref, remote_parent_ref),"
            "    UNIQUE(remote_ref, local_path))"
        )

    @staticmethod
    def _create_transfer_tables(cursor: Cursor, /) -> None:
        """Create the Uploads and Downloads tables."""
        cursor.execute(
            "CREATE TABLE Downloads ("
            "    uid            INTEGER     NOT NULL,"
            "    path           VARCHAR     UNIQUE,"
            "    status         INTEGER,"
            "    engine         VARCHAR     DEFAULT NULL,"
            "    is_direct_edit INTEGER     DEFAULT 0,"
            "    progress       REAL,"
            "    filesize       INTEGER     DEFAULT 0,"
            "    doc_pair       INTEGER     UNIQUE,"
            "    tmpname        VARCHAR,"
            "    url            VARCHAR,"
            "    PRIMARY KEY (uid)"
            ")"
        )
        cursor.execute(
            "CREATE TABLE Uploads ("
            "    uid                INTEGER     NOT NULL,"
            "    path               VARCHAR,"
            "    status             INTEGER,"
            "    engine             VARCHAR     DEFAULT NULL,"
            "    is_direct_edit     INTEGER     DEFAULT 0,"
            "    is_direct_transfer INTEGER     DEFAULT 0,"
            "    progress           REAL,"
            "    filesize           INTEGER     DEFAULT 0,"
            "    doc_pair           INTEGER     UNIQUE,"
            "    batch              VARCHAR,"
            "    chunk_size         INTEGER,"
            "    remote_parent_path VARCHAR     DEFAULT NULL,"
            "    remote_parent_ref  VARCHAR     DEFAULT NULL,"
            "    request_uid        VARCHAR     DEFAULT NULL,"
            "    PRIMARY KEY (uid)"
            ")"
        )

    @staticmethod
    def _create_sessions_table(cursor: Cursor, /) -> None:
        """Create the Sessions table."""
        cursor.execute(
            "CREATE TABLE Sessions ("
            "    uid            INTEGER     NOT NULL,"
            "    status         INTEGER,"
            "    remote_ref     VARCHAR,"
            "    remote_path    VARCHAR,"
            "    uploaded       INTEGER     DEFAULT (0),"
            "    total          INTEGER,"
            "    engine         VARCHAR     DEFAULT '',"
            "    created_on     DATETIME    NOT NULL    DEFAULT CURRENT_TIMESTAMP,"
            "    completed_on   DATETIME,"
            "    description    VARCHAR     DEFAULT '',"
            "    planned_items  INTEGER,"
            "    PRIMARY KEY (uid)"
            ")"
        )

    @staticmethod
    def _create_session_items_table(cursor: Cursor, /) -> None:
        """Create the SessionItems table."""
        cursor.execute(
            "CREATE TABLE SessionItems ("
            "    session_id     INTEGER     NOT NULL,"
            "    data           VARCHAR     NOT NULL)"
        )


migration = MigrationInitial()
