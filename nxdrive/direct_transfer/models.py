# coding: utf-8
"""
The Direct Transfer feature.

What: SQL models.
"""
import json
from pathlib import Path

from nuxeo.models import Batch
from peewee import (
    BooleanField,
    CharField,
    DateTimeField,
    Field,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
)

from ..constants import TransferStatus

# https://sqlite.org/pragma.html
PRAGMAS = (
    ("foreign_keys", 1),
    ("journal_mode", "wal"),
    ("synchronous", 3),
    ("wal_checkpoint", 100),
)

# Note: using None instead of a the real database file, it will be set later
#       via DATABASE.init(FILE) in DirectTransferManager.init_db().
DATABASE = SqliteDatabase(None, check_same_thread=False, pragmas=PRAGMAS)


def empty_batch() -> Batch:
    """Empty batch for BatchField."""
    return Batch()


class BaseModel(Model):
    """Base class for all models."""

    class Meta:
        """The database to use for all models."""

        database = DATABASE
        only_save_dirty = True


class BatchField(Field):
    """Custom field to handle Batch objects."""

    field_type = "batch"
    unserializable = {"blobs"}

    def db_value(self, batch: Batch) -> str:
        """Convert the Batch to a serialized dict for database storage.
        Any value that cannot be serialized is wiped out.
        """
        obj = {k: v for k, v in batch.as_dict().items() if k not in self.unserializable}
        return json.dumps(obj)

    def python_value(self, batch: str) -> Batch:
        """Get back the Batch from the stored serialized dict (string)."""
        return Batch(**json.loads(batch))


class PathField(Field):
    """Custom field to handle Path objects."""

    field_type = "path"

    def db_value(self, value: Path) -> str:
        """Convert the path to a string for database storage."""
        return str(value)

    def python_value(self, value: str) -> Path:
        """Get back the path from the stored string."""
        return Path(value)


class StatusField(Field):
    """Custom field to handle TransferStatus objects."""

    field_type = "status"

    def db_value(self, status: TransferStatus) -> int:
        """Convert the path to a string for database storage."""
        return int(status.value)

    def python_value(self, status: int) -> TransferStatus:
        """Get back the path from the stored string."""
        return TransferStatus(status)


class Session(BaseModel):
    """Represent a Direct Transfer session.
    A session is a batch of transfers: each time a new Direct Transfer is initiated, a new session is created.
    """

    finished = DateTimeField(null=True)
    priority = IntegerField(default=0)
    started = DateTimeField(null=True)
    status = StatusField(default=TransferStatus.ONGOING)


class Transfer(BaseModel):
    """Represent a Direct Transfer item."""

    session = ForeignKeyField(Session)
    local_path = PathField()
    remote_path = CharField()
    # Keep those alphabetically sorted
    batch = BatchField(default=empty_batch)
    chunk_size = IntegerField(default=0)
    doctype = CharField(null=True)
    error_count = IntegerField(default=0)
    error_count_total = IntegerField(default=0)
    file_size = IntegerField(default=0)
    is_file = BooleanField(default=False)
    remote_ref = CharField(null=True)
    replace_blob = BooleanField(default=False)
    status = StatusField(default=TransferStatus.ONGOING)
    uploaded_size = IntegerField(default=0)
    uploaded = BooleanField(default=False)

    class Meta:
        """Create indexes."""

        indexes = (
            # Create a unique on session/local_path/remote_path combination
            (("session", "local_path", "remote_path"), True),
        )


MODELS = [Session, Transfer]
