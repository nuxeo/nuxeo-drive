"""Adding last_event_log_id to server_bindings

Revision ID: 2f126b5f61a6
Revises: 4f23a55ef249
Create Date: 2014-09-04 16:33:12.880669

"""

# revision identifiers, used by Alembic.
revision = '2f126b5f61a6'
down_revision = '4f23a55ef249'

from alembic import op
import sqlalchemy as sa
from nxdrive.logging_config import get_logger
from nxdrive.engine.dao.model import ServerBinding

log = get_logger(__name__)


def upgrade():
    op.add_column(ServerBinding.__tablename__,
                  sa.Column('last_event_log_id', sa.Integer()))


def downgrade():
    log.info("As SQLite doesn't support DROP COLUMN, leaving 'server_bindings'"
             " table unchanged, keeping 'last_event_log_id' column")
