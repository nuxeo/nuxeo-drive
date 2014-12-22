'''
Created on 17 oct. 2014

@author: Remi Cattiau
'''
from PyQt4.QtCore import QObject


class DAO(QObject):
    '''
    classdocs
    '''

    def __init__(self, params):
        '''
        Constructor
        '''

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