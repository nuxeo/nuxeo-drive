from nxdrive.engine.engine import Worker
import sqlite3
import os
from threading import Lock, local
from nxdrive.engine.dao.model import PAIR_STATES
from datetime import datetime
from nxdrive.logging_config import get_logger
log = get_logger(__name__)


class CustomRow(sqlite3.Row):
    _custom = None
    def __init__(self, arg1, arg2):
        super(CustomRow, self).__init__(arg1, arg2)
        self._custom = dict()

    def __getattr__(self, name):
        if name in self._custom:
            return self._custom[name]
        return self[name]

    def is_readonly(self):
        if self.folderish:
            return self.remote_can_create_child == 0
        else:
            return (self.remote_can_delete & self.remote_can_rename
                        & self.remote_can_update) == 0

    def update_state(self, local_state=None, remote_state=None):
        if local_state is not None:
            self.local_state = local_state
        if remote_state is not None:
            self.remote_state = remote_state

    def __setattr__(self, name, value):
        if name.startswith('_'):
            super(CustomRow, self).__setattr__(name,value)
        else:
            self._custom[name] = value

    def __delattr__(self, name):
        if name.startswith('_'):
            super(CustomRow, self).__detattr__(name)
        else:
            del self._custom[name]

    def __repr__(self):
        return "%s[%d](Local:%s, Remote:%s, State: %s)" % (self.__class__.__name__, self.id,
                                                        self.local_path, self.remote_ref, self.pair_state)


class FakeLock(object):
    def acquire(self):
        pass

    def release(self):
        pass

class SqliteDAO(Worker):
    '''
    classdocs
    '''

    def __init__(self, engine, db):
        '''
        Constructor
        '''
        super(SqliteDAO, self).__init__(engine)
        self._db = db
        # For testing purpose only should always be True
        self.share_connection = True
        self.auto_commit = True
        self._queue_manager = None

        # If we dont share connection no need to lock
        if self.share_connection:
            self._lock = Lock()
        else:
            self._lock = FakeLock()

        self._conn = sqlite3.connect(self._db, check_same_thread=False)
        # FOR PYTHON 3.3...
        #if log.getEffectiveLevel() < 6:
        #    self._conn.set_trace_callback(self._log_trace)
        c = self._conn.cursor()
        c.execute("CREATE TABLE if not exists Configuration(name VARCHAR NOT NULL, value VARCHAR, PRIMARY KEY (name))")
        c.execute("CREATE TABLE if not exists States(id INTEGER NOT NULL, last_local_updated TIMESTAMP,"
                  + "last_remote_updated TIMESTAMP, local_digest VARCHAR, remote_digest VARCHAR, local_path VARCHAR,"
                  + "remote_ref VARCHAR, local_parent_path VARCHAR, remote_parent_ref VARCHAR, remote_parent_path VARCHAR,"
                  + "local_name VARCHAR, remote_name VARCHAR, folderish INTEGER, local_state VARCHAR DEFAULT('unknown'), remote_state VARCHAR DEFAULT('unknown'),"
                  + "pair_state VARCHAR DEFAULT('unknown'), remote_can_rename INTEGER, remote_can_delete INTEGER, remote_can_update INTEGER,"
                  + "remote_can_create_child INTEGER, last_remote_modifier VARCHAR,"
                  + "last_sync_date TIMESTAMP, error_count INTEGER DEFAULT (0), last_sync_error_date TIMESTAMP, version INTEGER DEFAULT (0), processor INTEGER DEFAULT (0), PRIMARY KEY (id));")
        self._conn.row_factory = CustomRow
        self.reinit_processors()
        self._conn.commit()
        self._conns = local()

    def _log_trace(self, query):
        log.trace(query)

    def _get_write_connection(self):
        if self.share_connection:
            return self._conn
        return self._get_read_connection()

    def _get_read_connection(self):
        if not hasattr(self._conns, '_conn'):
            self._conns._conn = sqlite3.connect(self._db)
            self._conns._conn.row_factory = CustomRow
            # Python3.3 feature
            #if log.getEffectiveLevel() < 6:
            #    self._conns._conn.set_trace_callback(self._log_trace)
        return self._conns._conn

    def commit(self):
        self._lock.acquire()
        self._get_write_connection().commit()
        self._lock.release()

    def release_processor(self, processor_id):
        self._lock.acquire()
        con = self._get_write_connection()
        c = con.cursor()
        c.execute("UPDATE States SET processor=0 WHERE processor=?", (processor_id,))
        if self.auto_commit:
            con.commit()
        self._lock.release()
        return c.rowcount == 1

    def acquire_processor(self, thread_id, row_id):
        self._lock.acquire()
        con = self._get_write_connection()
        c = con.cursor()
        c.execute("UPDATE States SET processor=? WHERE id=? AND processor=0", (thread_id, row_id))
        if self.auto_commit:
            con.commit()
        self._lock.release()
        return c.rowcount == 1

    def reinit_processors(self):
        self._lock.acquire()
        con = self._get_write_connection()
        c = con.cursor()
        c.execute("UPDATE States SET processor=0")
        if self.auto_commit:
            con.commit()
        self._lock.release()

    def delete_local_state(self, row):
        print "SHOULD NOT DELETE YET"
        pass

    def insert_local_state(self, info, parent_path):
        pair_state = PAIR_STATES.get(('created', 'unknown'))
        digest = info.get_digest()
        self._lock.acquire()
        con = self._get_write_connection()
        c = con.cursor()
        name = os.path.basename(info.path)
        c.execute("INSERT INTO States(last_local_updated, local_digest, "
                  + "local_path, local_parent_path, local_name, folderish, local_state, remote_state, pair_state)"
                  + " VALUES(?,?,?,?,?,?,'created','unknown',?)", (info.last_modification_time, digest, info.path,
                                                parent_path, name, info.folderish, pair_state))
        row_id = c.lastrowid
        self._queue_pair_state(row_id, info.folderish, pair_state)
        if self.auto_commit:
            con.commit()
        self._lock.release()
        return row_id

    def register_queue_manager(self, manager):
        # Prevent any update while init queue
        self._lock.acquire()
        try:
            self._queue_manager = manager
            con = self._get_write_connection()
            c = con.cursor()
            res = c.execute("SELECT * FROM States WHERE pair_state != 'synchronized' AND pair_state != 'unsynchronized'")
            self._queue_manager.init_queue(res.fetchall())
        # Dont block everything if queue manager fail
        # TODO As the error should be fatal not sure we need this
        finally:
            self._lock.release()

    def _queue_pair_state(self, row_id, folderish, pair_state):
        if (self._queue_manager is not None
             and pair_state != 'synchronized' and pair_state != 'unsynchronized'):
            self._queue_manager.push_ref(row_id, folderish, pair_state)
        return

    def _get_pair_state(self, row):
        return PAIR_STATES.get((row.local_state, row.remote_state))

    def update_local_state(self, row, info, versionned=True, queue=True):
        pair_state = self._get_pair_state(row)
        version = ''
        if versionned:
            version = ', version=version+1'
        self._lock.acquire()
        con = self._get_write_connection()
        c = con.cursor()
        # Should not update this
        c.execute("UPDATE States SET last_local_updated=?, local_digest=?, local_path=?, local_name=?,"
                  + "local_state=?, remote_state=?, pair_state=?" + version +
                  " WHERE id=?", (info.last_modification_time, row.local_digest, info.path, 
                                    os.path.basename(info.path), row.local_state, row.remote_state,
                                    pair_state, row.id))
        if row.pair_state != pair_state and queue:
            self._queue_pair_state(row.id, info.folderish, pair_state)
        if self.auto_commit:
            con.commit()
        self._lock.release()

    def get_valid_duplicate_file(self, digest):
        c = self._get_read_connection().cursor()
        return c.execute("SELECT * FROM States WHERE remote_digest=? AND pair_state='synchronized'", (digest,)).fetchone()

    def get_remote_children(self, ref):
        c = self._get_read_connection().cursor()
        return c.execute("SELECT * FROM States WHERE remote_parent_ref=?", (ref,)).fetchall()

    def get_local_children(self, path):
        c = self._get_read_connection().cursor()
        return c.execute("SELECT * FROM States WHERE local_parent_path=?", (path,)).fetchall()

    def get_states_from_partial_local(self, path):
        c = self._get_read_connection().cursor()
        return c.execute("SELECT * FROM States WHERE local_path LIKE '" + path + "%'").fetchall()

    def get_states_from_partial_remote(self, ref):
        c = self._get_read_connection().cursor()
        return c.execute("SELECT * FROM States WHERE remote_ref LIKE '%" + ref + "'").fetchall()

    def get_states_from_remote(self, ref):
        c = self._get_read_connection().cursor()
        return c.execute("SELECT * FROM States WHERE remote_ref=?", (ref,)).fetchall()

    def get_state_from_id(self, row_id, from_write=False):
        # Dont need to read from write as auto_commit is True
        if from_write and self.auto_commit:
            from_write = False
        if from_write:
            self._lock.acquire()
            c = self._get_write_connection().cursor()
        else:
            c = self._get_read_connection().cursor()
        state = c.execute("SELECT * FROM States WHERE id=?", (row_id,)).fetchone()
        if from_write:
            self._lock.release()
        return state

    def _get_recursive_condition(self, doc_pair):
        return (" WHERE local_parent_path LIKE '" + doc_pair.local_path + "/%'"
                    + " OR local_parent_path = '" + doc_pair.local_path + "'")

    def mark_descendants_remotely_created(self, doc_pair):
        self._lock.acquire()
        con = self._get_write_connection()
        c = con.cursor()
        update = "UPDATE States SET local_digest=NULL, last_local_updated=NULL, local_name=NULL"
        c.execute(update + " WHERE id=?", doc_pair.id)
        if doc_pair.folderish:
            c.execute(update + self._get_recursive_condition(doc_pair))
        if self.auto_commit:
            con.commit()
        self._lock.release()

    def remove_pair(self, doc_pair):
        self._lock.acquire()
        con = self._get_write_connection()
        c = con.cursor()
        c.execute("DELETE FROM States WHERE id=?", doc_pair.id)
        if doc_pair.folderish:
            c.execute("DELETE FROM States" + self._get_recursive_condition(doc_pair))
        if self.auto_commit:
            con.commit()
        self._lock.release()

    def get_state_from_local(self, path):
        c = self._get_read_connection().cursor()
        return c.execute("SELECT * FROM States WHERE local_path=?", (path,)).fetchone()

    def insert_remote_state(self, info, remote_parent_path, local_path, local_parent_path):
        pair_state = PAIR_STATES.get(('unknown','created'))
        self._lock.acquire()
        con = self._get_write_connection()
        c = con.cursor()
        c.execute("INSERT INTO States (remote_ref, remote_parent_ref, " +
                  "remote_parent_path, remote_name, last_remote_updated, remote_can_rename," +
                  "remote_can_delete, remote_can_update, " +
                  "remote_can_create_child, last_remote_modifier, remote_digest," +
                  "folderish, last_remote_modifier, local_path, local_parent_path, remote_state, local_state, pair_state)" +
                  " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'created','unknown',?)",
                  (info.uid, info.parent_uid, remote_parent_path, info.name,
                   info.last_modification_time, info.can_rename, info.can_delete, info.can_update,
                   info.can_create_child, info.last_contributor, info.digest, info.folderish, info.last_contributor,
                   local_path, local_parent_path, pair_state))
        row_id = c.lastrowid
        self._queue_pair_state(row_id, info.folderish, pair_state)
        if self.auto_commit:
            con.commit()
        self._lock.release()
        return row_id

    def synchronize_state(self, row, version=None, state='synchronized'):
        if version is None:
            version = row.version
        self._lock.acquire()
        con = self._get_write_connection()
        log.trace("Put sync pair [%d] as %s", row.id, state)
        c = con.cursor()
        c.execute("UPDATE States SET local_state='synchronized', remote_state='synchronized', " +
                  "pair_state=?, last_sync_date=?, processor = 0 " +
                  "WHERE id=? and version=?",
                  (state, datetime.utcnow(), row.id, version))
        if self.auto_commit:
            con.commit()
        self._lock.release()
        return c.rowcount == 1

    def update_remote_state(self, row, info, remote_parent_path=None, versionned=True):
        pair_state = self._get_pair_state(row)
        if remote_parent_path is None:
            remote_parent_path = row.remote_parent_path
        version = ''
        if versionned:
            version = ', version=version+1'
        self._lock.acquire()
        con = self._get_write_connection()
        c = con.cursor()
        c.execute("UPDATE States SET remote_ref=?, remote_parent_ref=?, " +
                  "remote_parent_path=?, remote_name=?, last_remote_updated=?, remote_can_rename=?," +
                  "remote_can_delete=?, remote_can_update=?, " +
                  "remote_can_create_child=?, last_remote_modifier=?, remote_digest=?, local_state=?," +
                  "remote_state=?, pair_state=?, last_remote_modifier=?" + version + " WHERE id=?",
                  (info.uid, info.parent_uid, remote_parent_path, info.name,
                   info.last_modification_time, info.can_rename, info.can_delete, info.can_update,
                   info.can_create_child, info.last_contributor, info.digest, row.local_state,
                   row.remote_state, pair_state, info.last_contributor, row.id))
        if row.pair_state != pair_state:
            self._queue_pair_state(row.id, info.folderish, pair_state)
        if self.auto_commit:
            con.commit()
        self._lock.release()

    def is_filter(self, path):
        pass

    def get_filter(self):
        pass

    def get_filters(self):
        pass

    def add_filter(self):
        pass

    def remove_filter(self):
        pass

    def update_config(self, name, value):
        self._lock.acquire()
        con = self._get_write_connection()
        c = con.cursor()
        c.execute("UPDATE OR IGNORE Configuration SET value=? WHERE name=?",(value,name))
        c.execute("INSERT OR IGNORE INTO Configuration(value,name) VALUES(?,?)",(value,name))
        if self.auto_commit:
            con.commit()
        self._lock.release()

    def get_config(self, name, default=None):
        c = self._get_read_connection().cursor()
        obj = c.execute("SELECT value FROM Configuration WHERE name=?",(name,)).fetchone()
        if obj is None:
            return default
        return obj.value