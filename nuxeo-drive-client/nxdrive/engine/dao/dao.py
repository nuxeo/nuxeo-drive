'''
Created on 17 oct. 2014

@author: Remi Cattiau
'''
from PyQt4.QtCore import QObject
from nxdrive.engine.dao.model import LastKnownState


class AlchemyDAO(QObject):
    def __init__(self, local_folder, session):
        super(AlchemyDAO, self).__init__()
        self.session = session
        self.local_folder = local_folder

    def get_local_children(self, path):
        result = self.session.query(LastKnownState).filter_by(
                local_folder=self.local_folder,
                local_parent_path=path)
        for r in result:
            self.session.expunge(r)
        return result

    def insert_local_state(self, info):
        state = LastKnownState(local_folder=self.local_folder, local_info=info)
        self.session.add(state)
        return state

    def update_local_state(self, row, info):
        row.update_local(info)
        return self.session.merge(row)

    def commit(self):
        self.session.commit()


class SqliteDAO(QObject):
    '''
    classdocs
    '''

    def __init__(self, db):
        '''
        Constructor
        '''
        super(SqliteDAO, self).__init__()
        self.db = db
        import sqlite3
        self.conn = sqlite3.connect(self.db)
        c = self.conn.cursor()
        c.execute("CREATE TABLE States()")

    def upsert_local_state(self, info):
        c = self.conn.cursor()
        pass

    def get_state(self):
        #session.expunge(obj)
        pass

    def save_state(self, object):
        #_save_state.emit(object)
        pass

    def update_local_state(self, id):
        pass

    def update_remote_state(self, id):
        pass

    def get_filter(self):
        pass

    def get_filters(self):
        pass

    def add_filter(self):
        pass

    def remove_filter(self):
        pass

    def update_config(self):
        pass
