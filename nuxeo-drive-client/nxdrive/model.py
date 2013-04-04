import os
import uuid
import logging
import datetime
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Sequence
from sqlalchemy import String
from sqlalchemy.orm import relationship
from sqlalchemy.orm import backref
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import scoped_session
from sqlalchemy.pool import SingletonThreadPool

from nxdrive.client import RemoteFileSystemClient
from nxdrive.client import LocalClient
from nxdrive.utils import normalized_path

WindowsError = None
try:
    from exceptions import WindowsError
except ImportError:
    # This will never be raised under unix
    pass


log = logging.getLogger(__name__)


# make the declarative base class for the ORM mapping
Base = declarative_base()


__model_version__ = 1

# Summary status from last known pair of states

PAIR_STATES = {
    # regular cases
    ('unknown', 'unknown'): 'unknown',
    ('synchronized', 'synchronized'): 'synchronized',
    ('created', 'unknown'): 'locally_created',
    ('unknown', 'created'): 'remotely_created',
    ('modified', 'synchronized'): 'locally_modified',
    ('synchronized', 'modified'): 'remotely_modified',
    ('modified', 'unknown'): 'locally_modified',
    ('unknown', 'modified'): 'remotely_modified',
    ('deleted', 'synchronized'): 'locally_deleted',
    ('synchronized', 'deleted'): 'remotely_deleted',
    ('deleted', 'deleted'): 'deleted',

    # conflicts with automatic resolution
    ('created', 'deleted'): 'locally_created',
    ('deleted', 'created'): 'remotely_created',
    ('modified', 'deleted'): 'locally_created',
    ('deleted', 'modified'): 'remotely_created',

    # conflict cases that need special
    ('modified', 'modified'): 'conflicted',
    ('created', 'created'): 'conflicted',
}


class DeviceConfig(Base):
    """Holds Nuxeo Drive configuration parameters

    This is expected to be a single row table.
    """
    __tablename__ = 'device_config'

    device_id = Column(String, primary_key=True)

    def __init__(self, device_id=None):
        self.device_id = uuid.uuid1().hex if device_id is None else device_id


class ServerBinding(Base):
    __tablename__ = 'server_bindings'

    local_folder = Column(String, primary_key=True)
    server_url = Column(String)
    remote_user = Column(String)
    remote_password = Column(String)
    remote_token = Column(String)
    last_sync_date = Column(Integer)
    last_root_definitions = Column(String)

    def __init__(self, local_folder, server_url, remote_user,
                 remote_password=None, remote_token=None):
        self.local_folder = local_folder
        self.server_url = server_url
        self.remote_user = remote_user
        # Password is only stored if the server does not support token based
        # auth
        self.remote_password = remote_password
        self.remote_token = remote_token

    def invalidate_credentials(self):
        """Ensure that all stored credentials are zeroed."""
        self.remote_password = None
        self.remote_token = None

    def has_invalid_credentials(self):
        """Check whether at least one credential is active"""
        return self.remote_password is None and self.remote_token is None


class LastKnownState(Base):
    """Aggregate state aggregated from last collected events."""
    __tablename__ = 'last_known_states'

    id = Column(Integer, Sequence('state_id_seq'), primary_key=True)

    local_folder = Column(String, ForeignKey('server_bindings.local_folder'),
                          index=True)
    server_binding = relationship(
        'ServerBinding',
        backref=backref("states", cascade="all, delete-orphan"))

    # Timestamps to detect modifications
    last_local_updated = Column(DateTime)
    last_remote_updated = Column(DateTime)

    # Save the digest too for better updates / moves detection
    local_digest = Column(String, index=True)
    remote_digest = Column(String, index=True)

    # Path from root using unix separator, '/' for the root it-self.
    local_path = Column(String, index=True)

    # Remote reference (instead of path based lookup)
    remote_ref = Column(String, index=True)

    # Parent path from root / ref for fast children queries,
    # can be None for the root it-self.
    local_parent_path = Column(String, index=True)
    remote_parent_ref = Column(String, index=True)
    remote_parent_path = Column(String)  # for ordering only

    # Names for fast alignment queries
    local_name = Column(String, index=True)
    remote_name = Column(String, index=True)

    folderish = Column(Integer)

    # Last known state based on event log
    local_state = Column(String)
    remote_state = Column(String)
    pair_state = Column(String, index=True)

    # TODO: remove since unused, but might brake
    # previous Nuxeo Drive client installations
    # Track move operations to avoid losing history
    locally_moved_from = Column(String)
    locally_moved_to = Column(String)
    remotely_moved_from = Column(String)
    remotely_moved_to = Column(String)

    # Flags for remote write operations
    remote_can_rename = Column(Integer)
    remote_can_delete = Column(Integer)
    remote_can_update = Column(Integer)
    remote_can_create_child = Column(Integer)

    # Log date of sync errors to be able to skip documents in error for some
    # time
    last_sync_error_date = Column(DateTime)

    def __init__(self, local_folder, local_info=None,
                 remote_info=None, local_state='unknown',
                 remote_state='unknown'):
        self.local_folder = local_folder
        if local_info is None and remote_info is None:
            raise ValueError(
                "At least local_info or remote_info should be provided")

        if local_info is not None:
            self.update_local(local_info)
        if remote_info is not None:
            self.update_remote(remote_info)

        self.update_state(local_state=local_state, remote_state=remote_state)

    def update_state(self, local_state=None, remote_state=None):
        if local_state is not None and self.local_state != local_state:
            self.local_state = local_state
        if remote_state is not None and self.remote_state != remote_state:
            self.remote_state = remote_state

        # Detect heuristically aligned situations
        if (self.local_path is not None and self.remote_ref is not None
            and self.local_state == self.remote_state == 'unknown'):
            if self.folderish or self.local_digest == self.remote_digest:
                self.local_state = 'synchronized'
                self.remote_state = 'synchronized'

        pair = (self.local_state, self.remote_state)
        pair_state = PAIR_STATES.get(pair, 'unknown')
        if self.pair_state != pair_state:
            self.pair_state = pair_state

    def __repr__(self):
        return ("LastKnownState<local_folder=%r, local_path=%r, "
                "remote_name=%r, local_state=%r, remote_state=%r>") % (
                    os.path.basename(self.local_folder),
                    self.local_path, self.remote_name,
                    self.local_state, self.remote_state)

    def get_local_client(self):
        return LocalClient(self.local_folder)

    def get_remote_client(self):
        sb = self.server_binding
        return RemoteFileSystemClient(sb.server_url, sb.remote_user,
             sb.remote_password)

    def refresh_local(self, client=None, local_path=None):
        """Update the state from the local filesystem info."""
        client = client if client is not None else self.get_local_client()
        local_path = local_path if local_path is not None else self.local_path
        local_info = client.get_info(local_path, raise_if_missing=False)
        self.update_local(local_info)
        return local_info

    def update_local(self, local_info):
        """Update the state from pre-fetched local filesystem info."""
        if local_info is None:
            if self.local_state in ('unknown', 'created', 'modified',
                                    'synchronized'):
                # the file use to exist, it has been deleted
                self.update_state(local_state='deleted')
            return

        local_state = None

        if self.local_path is None or self.local_path != local_info.path:
            # Either this state only has a remote info and this is the
            # first time we update the local info from the file system,
            # or it is a renaming
            self.local_path = local_info.path
            if self.local_path != '/':
                self.local_name = os.path.basename(local_info.path)
                local_parent_path, _ = local_info.path.rsplit('/', 1)
                if local_parent_path == '':
                    self.local_parent_path = '/'
                else:
                    self.local_parent_path = local_parent_path
            else:
                self.local_name = os.path.basename(self.local_folder)
                self.local_parent_path = None

        # Shall we recompute the digest from the current file?
        update_digest = self.local_digest == None

        if self.last_local_updated is None:
            self.last_local_updated = local_info.last_modification_time
            self.folderish = local_info.folderish
            update_digest = True

        elif local_info.last_modification_time > self.last_local_updated:
            self.last_local_updated = local_info.last_modification_time
            self.folderish = local_info.folderish
            if not self.folderish:
                # The time stamp of folderish folder seems to be updated when
                # children are added under Linux? Is this the same under OSX
                # and Windows?
                local_state = 'modified'
            update_digest = True

        if update_digest:
            try:
                self.local_digest = local_info.get_digest()
            except (IOError, WindowsError):
                # This can fail when another process is writing the same file
                # let's postpone digest computation in that case
                log.debug("Delaying local digest computation for %r"
                          " due to possible concurrent file access.",
                          local_info.filepath)

        # XXX: shall we store local_folderish and remote_folderish to
        # detect such kind of conflicts instead?
        self.update_state(local_state=local_state)

    def refresh_remote(self, client=None):
        """Update the state from the remote server info.

        Can reuse an existing client to spare some redundant client init HTTP
        request.
        """
        client = client if client is not None else self.get_remote_client()
        remote_info = client.get_info(self.remote_ref, raise_if_missing=False)
        self.update_remote(remote_info)
        return remote_info

    def update_remote(self, remote_info):
        """Update the state from the pre-fetched remote server info."""
        if remote_info is None:
            if self.remote_state in ('unknown', 'created', 'modified',
                                     'synchronized'):
                self.update_state(remote_state='deleted')
            return

        remote_state = None
        if self.remote_ref is None:
            self.remote_ref = remote_info.uid
            self.remote_parent_ref = remote_info.parent_uid

        if self.remote_ref != remote_info.uid:
            raise ValueError("State %r (%s) cannot be mapped to remote"
                             " doc %r (%s)" % (
                self, self.remote_ref, remote_info.name, remote_info.uid))

        # Use last known modification time to detect updates
        if self.last_remote_updated is None:
            self.last_remote_updated = remote_info.last_modification_time
        elif (remote_info.last_modification_time > self.last_remote_updated
            or self.remote_parent_ref != remote_info.parent_uid):
            # Remote update and/or rename and/or move
            self.last_remote_updated = remote_info.last_modification_time
            remote_state = 'modified'

        # Update the remaining metadata
        self.remote_digest = remote_info.get_digest()
        self.folderish = remote_info.folderish
        self.remote_name = remote_info.name
        suffix_len = len(remote_info.uid) + 1
        self.remote_parent_ref = remote_info.parent_uid
        self.remote_parent_path = remote_info.path[:-suffix_len]
        self.update_state(remote_state=remote_state)
        self.remote_can_rename = remote_info.can_rename
        self.remote_can_delete = remote_info.can_delete
        self.remote_can_update = remote_info.can_update
        self.remote_can_create_child = remote_info.can_create_child

    def get_local_abspath(self):
        relative_path = self.local_path[1:].replace('/', os.path.sep)
        return os.path.join(self.local_folder, relative_path)


class FileEvent(Base):
    __tablename__ = 'fileevents'

    id = Column(Integer, Sequence('fileevent_id_seq'), primary_key=True)
    local_folder = Column(String, ForeignKey('server_bindings.local_folder'))
    utc_time = Column(DateTime)
    path = Column(String)

    server_binding = relationship("ServerBinding")

    def __init__(self, local_folder, path, utc_time=None):
        self.local_folder = local_folder
        if utc_time is None:
            utc_time = datetime.utcnow()


def init_db(nxdrive_home, echo=False, scoped_sessions=True, poolclass=None):
    """Return an engine and session maker configured for using nxdrive_home

    The database is created in nxdrive_home if missing and the tables
    are intialized based on the model classes from this module (they
    all inherit the same abstract base class.

    If scoped_sessions is True, sessions built with this maker are reusable
    thread local singletons.

    """
    # We store the DB as SQLite files in the nxdrive_home folder
    dbfile = os.path.join(normalized_path(nxdrive_home), 'nxdrive.db')

    # SQLite cannot share connections across threads hence it's safer to
    # enforce this at the connection pool level
    poolclass = SingletonThreadPool if poolclass is None else poolclass
    engine = create_engine('sqlite:///' + dbfile, echo=echo,
                           poolclass=poolclass)

    # Ensure that the tables are properly initialized
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)
    if scoped_sessions:
        maker = scoped_session(maker)
    return engine, maker