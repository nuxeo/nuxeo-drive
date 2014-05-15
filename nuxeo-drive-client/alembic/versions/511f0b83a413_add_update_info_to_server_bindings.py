"""Add update info to server_bindings

New columns:
    - server_version: Column(String)
    - update_url: Column(String)

Revision ID: 511f0b83a413
Revises: None
Create Date: 2014-05-13 14:33:57.756364

"""

# revision identifiers, used by Alembic.
revision = '511f0b83a413'
down_revision = None

from alembic import op
import sqlalchemy as sa
from nxdrive.logging_config import get_logger
from nxdrive.model import ServerBinding

log = get_logger(__name__)


def upgrade():
    op.add_column(ServerBinding.__tablename__,
                  sa.Column('server_version', sa.String()))
    op.add_column(ServerBinding.__tablename__,
                  sa.Column('update_url', sa.String()))


def downgrade():
    log.info("As SQLite doesn't support DROP COLUMN, leaving 'server_bindings'"
             " table unchanged, keeping 'server_version' and 'update_url'"
             " columns")
