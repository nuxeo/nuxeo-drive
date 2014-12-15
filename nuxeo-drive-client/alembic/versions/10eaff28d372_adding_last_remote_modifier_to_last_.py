"""Adding last_remote_modifier to last_known_states

Revision ID: 10eaff28d372
Revises: 2f126b5f61a6
Create Date: 2014-12-15 14:31:30.499777

"""

# revision identifiers, used by Alembic.
revision = '10eaff28d372'
down_revision = '2f126b5f61a6'

from alembic import op
import sqlalchemy as sa
from nxdrive.logging_config import get_logger
from nxdrive.model import LastKnownState

log = get_logger(__name__)


def upgrade():
    op.add_column(LastKnownState.__tablename__,
                  sa.Column('last_remote_modifier', sa.String()))


def downgrade():
    log.info("As SQLite doesn't support DROP COLUMN, leaving 'last_known_states'"
             " table unchanged, keeping 'last_remote_modifier' column")
