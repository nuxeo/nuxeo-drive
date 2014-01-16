from nxdrive.logging_config import get_logger
from nxdrive.utils import find_resource_dir
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.environment import EnvironmentContext
from alembic import context

import os


log = get_logger(__name__)


def migrate_db(engine):
    """Upgrade given database engine to latest Alembic revision if needed."""
    config = Config()
    config.set_main_option("script_location", "alembic")
    upgrade(config, engine, 'head')


def upgrade(config, engine, revision):
    """Upgrade to the given revision."""

    script = from_config(config)

    def upgrade(rev, context):
        return script._upgrade_revs(revision, rev)

    # Always run full upgrade
    starting_rev = None
    with EnvironmentContext(
        config,
        script,
        fn=upgrade,
        as_sql=False,
        starting_rev=starting_rev,
        destination_rev=revision
    ):
        run_migration(engine)


def from_config(config):
    """Instantiate a ScriptDirectory from the given config using generic
    resource finder.
    """
    script_location = config.get_main_option('script_location')
    if script_location is None:
        raise RuntimeError("No 'script_location' key "
                                "found in configuration.")

    import nxdrive
    nxdrive_path = os.path.dirname(nxdrive.__file__)
    alembic_path = nxdrive_path.replace('nxdrive', script_location)

    return ScriptDirectory(
                find_resource_dir(script_location, alembic_path)
                )


def run_migration(engine):
    """Run migration within the current EnvironmentContext"""
    try:
        # Configure EnvironmentContext with database connection
        connection = engine.connect()
        context.configure(connection=connection)

        # Compare current and head revisions
        log.debug("Checking if SQLite database migration is needed.")
        migration_context = context.get_context()
        current_rev = migration_context.get_current_revision()
        head_rev = context.get_head_revision()
        log.debug("Current Alembic revision: %s", current_rev)
        log.debug("Head Alembic revision: %s", head_rev)

        # Only process migration if current revision is different from
        # head revision
        if current_rev == head_rev:
            log.debug("No migration to process as current Alembic revision in"
                      " SQLite database is already the head revision.")
        else:
            with context.begin_transaction():
                context.run_migrations()
            log.debug('Ended SQLite database migration')
    finally:
        connection.close()
