"""Database model for Nuxeo Drive"""

import os
import datetime
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import Sequence
from sqlalchemy import String
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# make the declarative base class for the ORM mapping
Base = declarative_base()


__model_version__ = 1


class ServerBinding(Base):
    __tablename__ = 'server_bindings'

    local_folder = Column(String, primary_key=True)
    remote_host = Column(String)
    remote_user = Column(String)
    remote_password = Column(String)

    def __init__(self, local_folder, remote_host, remote_user,
                 remote_password):
        self.local_folder = local_folder
        self.remote_host = remote_host
        self.remote_user = remote_user
        self.remote_password = remote_password


class RootBinding(Base):
    __tablename__ = 'root_bindings'

    local_root = Column(String, primary_key=True)
    remote_root = Column(String)
    local_folder = Column(String, ForeignKey('server_bindings.local_folder'))

    server_binding = relationship('ServerBinding')

    def __init__(self, local_root, remote_root):
        local_root = os.path.abspath(local_root)
        self.local_root = local_root
        self.remote_root = remote_root

        # expected local folder should be the direct parent of the
        local_folder = os.path.abspath(os.path.join(local_root, '..'))
        self.local_folder = local_folder


class FileEvent(Base):
    __tablename__ = 'fileevents'

    id = Column(Integer, Sequence('fileevent_id_seq'), primary_key=True)
    local_root = Column(String, ForeignKey('root_bindings.local_root'))
    utc_time = Column(DateTime)
    path = Column(String)

    root_binding = relationship("RootBinding")

    def __init__(self, local_root, path, utc_time=None):
        self.local_root = local_root
        if utc_time is None:
            utc_time = datetime.utcnow()


def get_session(nxdrive_home, echo=False):
    # We store the DB as SQLite files in the nxdrive_home folder
    dbfile = os.path.join(os.path.abspath(nxdrive_home), 'nxdrive.db')
    engine = create_engine('sqlite:///' + dbfile, echo=echo)

    # Ensure that the tables are properly initialized
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()
