'''
Created on Jul 13, 2016

@author: mkeshava
'''
from nxdrive.engine.workers import PollWorker
from datetime import timedelta, datetime
from nxdrive.logging_config import get_logger


USERNAME_UPDATE_INTERVAL = timedelta(days=1).total_seconds()
log = get_logger(__name__)


class UserNameResolver(PollWorker):
    '''
    A Polling Worker to refresh the userid to user's full name mapping everyday
    '''
    def __init__(self, engine):
        '''
        The polling interval is 1 day
        '''
        super(UserNameResolver, self).__init__(check_interval=USERNAME_UPDATE_INTERVAL)
        self._engine = engine

    def _poll(self):
        '''
            The poll action
        '''
        log.trace("Refreshing Users table")
        to_datetime = lambda text: datetime.strptime(text.split('.')[0], '%Y-%m-%d %H:%M:%S')
        start_time = datetime.now()
        # This method will retrieve the first 50 users for the current tenant (includes guest users also). This is re-using API meant for user search in DM UI
        self._engine.fetch_all_users()
        # For remaining users we userid to user full name resolution done by 'api/v1/user/<userid>'
        while True:
            to_refresh = self._engine._dao.get_next_user_to_resolve()
            if to_datetime(to_refresh.last_refreshed) >= start_time:
                break
            self._engine.get_user_full_name(to_refresh.user_id)
        log.trace("Completed refreshing Users table")
