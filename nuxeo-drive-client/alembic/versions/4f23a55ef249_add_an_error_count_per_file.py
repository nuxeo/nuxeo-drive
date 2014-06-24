"""Add an error count per file

Revision ID: 4f23a55ef249
Revises: 463dea770df1
Create Date: 2014-06-19 12:48:36.090929

"""

# revision identifiers, used by Alembic.
revision = '4f23a55ef249'
down_revision = '463dea770df1'

from alembic import op
import sqlalchemy as sa
from nxdrive.logging_config import get_logger
from nxdrive.model import LastKnownState

log = get_logger(__name__)


def upgrade():
    op.add_column(LastKnownState.__tablename__,
                  sa.Column('error_count', sa.Integer()))


def downgrade():
    log.info("As SQLite doesn't support DROP COLUMN, leaving 'device_config'"
             " table unchanged, keeping 'auto_update' column")
