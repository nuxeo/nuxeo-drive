import os
import uuid
import itertools
import logging
from datetime import datetime
from time import time
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Sequence
from sqlalchemy import String
from sqlalchemy import Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.orm import backref
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import scoped_session
from sqlalchemy.pool import SingletonThreadPool

from nxdrive import __version__
from nxdrive.utils import normalized_path
from nxdrive.logging_config import get_logger
from sqlalchemy.types import Binary

WindowsError = None
try:
    from exceptions import WindowsError
except ImportError:
    # This will never be raised under unix
    pass


log = get_logger(__name__)


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
    ('moved', 'synchronized'): 'locally_moved',
    ('moved', 'deleted'): 'locally_moved_created',
    ('synchronized', 'modified'): 'remotely_modified',
    ('modified', 'unknown'): 'locally_modified',
    ('unknown', 'modified'): 'remotely_modified',
    ('deleted', 'synchronized'): 'locally_deleted',
    ('synchronized', 'deleted'): 'remotely_deleted',
    ('deleted', 'deleted'): 'deleted',
    ('synchronized', 'unknown'): 'synchronized',

    # conflicts with automatic resolution
    ('created', 'deleted'): 'locally_created',
    ('deleted', 'created'): 'remotely_created',
    ('modified', 'deleted'): 'remotely_deleted',
    ('deleted', 'modified'): 'remotely_created',

    # conflict cases that need manual resolution
    ('modified', 'modified'): 'conflicted',
    ('created', 'created'): 'conflicted',

    # inconsistent cases
    ('unknown', 'deleted'): 'unknown_deleted',
    ('deleted', 'unknown'): 'deleted_unknown',
}

PROXY_TYPE_AUTO = 'System'
PROXY_TYPE_MANUAL = 'Manual'
PROXY_TYPE_NONE = 'None'


class DeviceConfig(Base):
    """Holds Nuxeo Drive configuration parameters

    This is expected to be a single row table.
    """
    __tablename__ = 'device_config'

    device_id = Column(String, primary_key=True)
    client_version = Column(String)

    # HTTP proxy settings
    # Possible values for proxy_config: System, None, Manual
    proxy_config = Column(String, default=PROXY_TYPE_AUTO)
    proxy_type = Column(String)
    proxy_server = Column(String)
    proxy_port = Column(String)
    proxy_authenticated = Column(Boolean)
    proxy_username = Column(String)
    proxy_password = Column(Binary)
    proxy_exceptions = Column(String)

    # Application update settings
    auto_update = Column(Boolean)

    def __init__(self, device_id=None, client_version=None):
        self.device_id = uuid.uuid1().hex if device_id is None else device_id
        self.client_version = (__version__ if client_version is None
                               else client_version)
        log.debug("Set client version to %s", self.client_version)

    def __repr__(self):
        return ("DeviceConfig<device_id=%s, client_version=%s, "
                "proxy_config=%s, proxy_type=%s, "
                "proxy_server=%s, proxy_port=%s, proxy_authenticated=%r, "
                "proxy_username=%s, proxy_exceptions=%s, auto_update=%r>") % (
                    self.device_id, self.client_version,
                    self.proxy_config, self.proxy_type,
                    self.proxy_server, self.proxy_port,
                    self.proxy_authenticated, self.proxy_username,
                    self.proxy_exceptions, self.auto_update)


class ServerBinding(Base):
    __tablename__ = 'server_bindings'

    local_folder = Column(String, primary_key=True)
    server_url = Column(String)
    remote_user = Column(String)
    remote_password = Column(String)
    remote_token = Column(String)
    server_version = Column(String)
    update_url = Column(String)
    last_sync_date = Column(Integer)
    last_event_log_id = Column(Integer)
    last_filter_date = Column(Integer)
    last_ended_sync_date = Column(Integer)
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
    error_count = Column(Integer, default=0)

    # Last sync date
    last_sync_date = Column(DateTime)

    # Log date of sync errors to be able to skip documents in error for some
    # time
    last_sync_error_date = Column(DateTime)

    # Avoid not in clauses (temporary marker)
    in_clause_selected = Column(Integer, default=0)

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

        self.error_count = 0

    def update_state(self, local_state=None, remote_state=None):
        if local_state is not None and self.local_state != local_state:
            self.local_state = local_state
        if remote_state is not None and self.remote_state != remote_state:
            self.remote_state = remote_state

        # Detect heuristically aligned situations
        if (self.local_path is not None and self.remote_ref is not None
            and self.local_state == self.remote_state == 'unknown'):
            # If folder or same digest consider as synchronized
            if self.folderish or self.local_digest == self.remote_digest:
                self.local_state = 'synchronized'
                self.remote_state = 'synchronized'
            # If a file has been modified on either one side or the other
            # consider the situation as a conflict. We cannot reasonably
            # decide which one of the local or remote versions is the 'right'
            # one has their history might have diverged. So trying to compare
            # last_local_updated and last_remote_updated would not be relevant
            # here.
            else:
                self.local_state = 'modified'
                self.remote_state = 'modified'

        pair = (self.local_state, self.remote_state)
        pair_state = PAIR_STATES.get(pair, 'unknown')
        if self.pair_state != pair_state:
            self.pair_state = pair_state
            log.trace("Updated state for LastKnownState<"
                      "local_folder=%r, local_path=%r, remote_name=%r,"
                      " local_state=%r, remote_state=%r, pair_state=%r>",
                      self.local_folder, self.local_path, self.remote_name,
                      self.local_state, self.remote_state, self.pair_state)

    def __repr__(self):
        return ("LastKnownState<local_folder=%r, local_path=%r, "
                "remote_name=%r, local_state=%r, remote_state=%r, "
                "pair_state=%r, error_count=%d>") % (
                    os.path.basename(self.local_folder),
                    self.local_path, self.remote_name,
                    self.local_state, self.remote_state,
                    self.pair_state, self.error_count)

    @staticmethod
    def select_remote_refs(session, refs, page_size):
        """Mark remote refs as selected"""
        tag = time()
        page_offset = 0
        log.trace("Selecting refs %r", refs)
        while (page_offset < len(refs)):
            page_refs = itertools.islice(refs, page_offset,
                            page_offset + page_size, None)
            session.query(LastKnownState).filter(
                            LastKnownState.remote_ref.in_(page_refs)).update(
                            {'in_clause_selected': tag},
                            synchronize_session=False)
            page_offset += page_size
        return tag

    @staticmethod
    def select_local_paths(session, paths, page_size):
        """Mark local paths as selected"""
        tag = time()
        page_offset = 0
        log.trace("Selecting paths %r", paths)
        while (page_offset < len(paths)):
            page_paths = itertools.islice(paths, page_offset,
                            page_offset + page_size, None)
            session.query(LastKnownState).filter(
                            LastKnownState.local_path.in_(page_paths)).update(
                            {'in_clause_selected': tag},
                            synchronize_session=False)
            page_offset += page_size
        return tag

    @staticmethod
    def not_selected(query, tag):
        return query.filter(LastKnownState.in_clause_selected != tag).all()

    @staticmethod
    def selected(query, tag):
        return query.filter(LastKnownState.in_clause_selected == tag).all()

    def refresh_local(self, client, local_path=None):
        """Update the state from the local filesystem info."""
        local_path = local_path if local_path is not None else self.local_path
        local_info = client.get_info(local_path, raise_if_missing=False)
        self.update_local(local_info)
        return local_info

    def update_local(self, local_info):
        """Update the state from pre-fetched local filesystem info."""
        if local_info is None:
            if self.local_state in ('unknown', 'created', 'modified',
                                    'synchronized'):
                # the file used to exist, it has been deleted
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

        elif local_info.last_modification_time != self.last_local_updated:
            self.last_local_updated = local_info.last_modification_time
            self.folderish = local_info.folderish
            # The time stamp of folderish folder seems to be updated when
            # children are added under Linux? Is this the same under OSX
            # and Windows?
            if not self.folderish:
                local_state = 'modified'
            else:
                if self.local_name == local_info.name:
                    # Folder for which the modification time has changed
                    # but not the name, this is a child update => align
                    # last synchronization date on last local update date
                    self.update_last_sync_date(self.last_local_updated)
            update_digest = True

        if update_digest:
            try:
                self.local_digest = local_info.get_digest()
            except (IOError, WindowsError) as e:
                # This can fail when another process is writing the same file
                # let's postpone digest computation in that case
                msg = ("Delaying local digest computation for %s"
                       " due to possible concurrent file access." %
                       local_info.filepath)
                if hasattr(e, 'msg'):
                    msg = msg + " " + e.msg
                log.debug(msg, exc_info=True)

        # XXX: shall we store local_folderish and remote_folderish to
        # detect such kind of conflicts instead?
        self.update_state(local_state=local_state)

    def refresh_remote(self, client):
        """Update the state from the remote server info."""
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
        log.trace("Use last known modification time to detect updates:"
                  " local DB, server = %r, %r",
                  (self.last_remote_updated.strftime('%Y-%m-%d %H:%M:%S')
                   if self.last_remote_updated else 'None'),
                  (remote_info.last_modification_time.strftime(
                                                    '%Y-%m-%d %H:%M:%S')
                  if remote_info.last_modification_time else 'None'))
        if self.last_remote_updated is None:
            self.last_remote_updated = remote_info.last_modification_time
            self.update_last_sync_date()
            log.trace("last_remote_updated is None for doc %s, set it to %s"
                      " and updated last_sync_date to %s",
                      self.remote_name, remote_info.last_modification_time,
                      self.last_sync_date)
        # Here checking that the remote modification time is strictly greater
        # than the one last updated in the DB should be fine, but in the case
        # of a version restore, the live document takes the modification time
        # of the version, which is necessarily (not strictly) lighter than
        # the one of the live document before restore, therefore we use the
        # 'not equal' predicate.
        elif (remote_info.last_modification_time != self.last_remote_updated
            or self.remote_parent_ref != remote_info.parent_uid):
            # Remote update and/or rename and/or move or restore from the trash
            log.trace("Doc %s has been either modified, renamed, moved or"
                      " restored from the trash,"
                      " set last_remote_updated to %s",
                      self.remote_name, remote_info.last_modification_time)
            self.last_remote_updated = remote_info.last_modification_time
            modified = False
            # Only consider a remote folder for which the modification time
            # has changed as modified if its name or its parent has changed
            # (rename or move)
            if (self.folderish
                and (self.remote_name != remote_info.name
                     or self.remote_parent_ref != remote_info.parent_uid)):
                log.trace("Doc %s is a folder that has been renamed or moved,"
                          " set remote_state to 'modified'",
                      self.remote_name)
                modified = True
            # Only consider a remote file for which the modification time has
            # changed as modified in the following cases:
            # - its name has changed (rename)
            # - its parent has changed (move)
            # - its content has changed (content update)
            # - its digest is different from the local one (can happen if
            # restored from the trash and content has been locally updated)
            if (not self.folderish
                and (self.remote_name != remote_info.name
                     or self.remote_parent_ref != remote_info.parent_uid
                     or self.remote_digest != remote_info.get_digest()
                     or self.remote_digest != self.local_digest)):
                log.trace("Doc %s is a file that has been renamed, moved,"
                          " for which the content has been updated or restored"
                          " from the trash, set remote_state to 'modified'",
                      self.remote_name)
                modified = True
            if modified:
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

    def is_readonly(self):
        if self.folderish:
            return self.remote_can_create_child == 0
        else:
            return (self.remote_can_delete & self.remote_can_rename
                        & self.remote_can_update) == 0

    def reset_local(self):
        self.local_digest = None
        self.local_name = None
        self.local_parent_path = None
        self.local_path = None
        self.local_state = 'unknown'

    def reset_remote(self):
        self.remote_digest = None
        self.remote_name = None
        self.remote_parent_path = None
        self.remote_parent_ref = None
        self.remote_ref = None
        self.local_state = 'unknown'

    def update_last_sync_date(self, last_sync_date=None):
        if last_sync_date is not None:
            self.last_sync_date = last_sync_date
        else:
            self.last_sync_date = datetime.now()

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


class Filter(Base):
    __tablename__ = 'filters'

    path = Column(String, primary_key=True)
    local_folder = Column(String, ForeignKey('server_bindings.local_folder'))

    server_binding = relationship("ServerBinding")

    def __init__(self, server_binding, path):
        if server_binding:
            self.local_folder = server_binding.local_folder
        else:
            self.local_folder = None
        self.path = Filter.clean_path(path)

    def __repr__(self):
        return self.path

    @staticmethod
    def is_filter(session, server_binding, path, filters=None):
        path = Filter.clean_path(path)
        if filters is None:
            filters = session.query(Filter).all()
        # Not the best way now need to move to count
        if any([path.startswith(filter_obj.path) for filter_obj in filters]):
            return True
        else:
            return False

    @staticmethod
    def add(session, server_binding, path):
        path = Filter.clean_path(path)
        if Filter.is_filter(session, server_binding, path):
            # Skip it as it is already filtered
            return
        # Remove any subfolders
        filters = session.query(Filter).filter(
                                            Filter.path.like(path + '%')).all()
        [session.delete(filter_obj) for filter_obj in filters]
        # Add the filter now
        filter_obj = Filter(server_binding, path)
        session.add(filter_obj)
        server_binding.last_filter_date = time()
        session.commit()

    @staticmethod
    def getAll(session, server_binding):
        return session.query(Filter).all()

    @staticmethod
    def clean_path(path):
        if not path.endswith("/"):
            path = path + "/"
        return path

    @staticmethod
    def remove(session, server_binding, path):
        path = Filter.clean_path(path)
        filters = session.query(Filter).filter(
                                            Filter.path.like(path + '%')).all()
        if len(filters) == 0:
            # Non existing filter
            return
        [session.delete(filter_obj) for filter_obj in filters]
        server_binding.last_filter_date = time()
        session.commit()


def init_db(nxdrive_home, echo=False, echo_pool=False, scoped_sessions=True,
            poolclass=None):
    """Return an engine and session maker configured for using nxdrive_home

    The database is created in nxdrive_home if missing and the tables
    are initialized based on the model classes from this module (they
    all inherit the same abstract base class.

    If scoped_sessions is True, sessions built with this maker are reusable
    thread local singletons.

    """
    # We store the DB as SQLite files in the nxdrive_home folder
    dbfile = os.path.join(normalized_path(nxdrive_home), 'nxdrive.db')

    # SQLite cannot share connections across threads hence it's safer to
    # enforce this at the connection pool level
    poolclass = SingletonThreadPool if poolclass is None else poolclass
    engine = create_engine('sqlite:///' + dbfile, poolclass=poolclass)

    # Configure SQLAlchemy logging
    if echo:
        logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)
    if echo_pool:
        logging.getLogger('sqlalchemy.pool').setLevel(logging.DEBUG)

    # Ensure that the tables are properly initialized
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)
    if scoped_sessions:
        maker = scoped_session(maker)
    return engine, maker
