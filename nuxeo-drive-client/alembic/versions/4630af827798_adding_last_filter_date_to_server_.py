"""Adding last_filter_date to server_bindings, and filters table

Revision ID: 4630af827798
Revises: 511f0b83a413
Create Date: 2014-05-22 12:10:02.930332

"""

# revision identifiers, used by Alembic.
revision = '4630af827798'
down_revision = '511f0b83a413'

from alembic import op
import sqlalchemy as sa
from nxdrive.logging_config import get_logger
from nxdrive.engine.dao.model import ServerBinding

log = get_logger(__name__)


def upgrade():
    op.add_column(ServerBinding.__tablename__, sa.Column('last_filter_date',
                                                         sa.Integer()))
    # The table filters should create itself


def downgrade():
    log.info("As SQLite doesn't support DROP COLUMN, leaving 'server_bindings'"
             " table unchanged, keeping 'last_filter_date' column")
