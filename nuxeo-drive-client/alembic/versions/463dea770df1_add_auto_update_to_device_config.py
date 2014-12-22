"""Add auto_update to device_config

Revision ID: 463dea770df1
Revises: 4630af827798
Create Date: 2014-05-27 17:07:28.141524

"""

# revision identifiers, used by Alembic.
revision = '463dea770df1'
down_revision = '4630af827798'

from alembic import op
import sqlalchemy as sa
from nxdrive.logging_config import get_logger
from nxdrive.engine.dao.model import DeviceConfig

log = get_logger(__name__)


def upgrade():
    op.add_column(DeviceConfig.__tablename__,
                  sa.Column('auto_update', sa.Boolean()))


def downgrade():
    log.info("As SQLite doesn't support DROP COLUMN, leaving 'device_config'"
             " table unchanged, keeping 'auto_update' column")
