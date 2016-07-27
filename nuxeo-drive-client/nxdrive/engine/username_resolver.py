'''
Created on Jul 13, 2016

@author: mkeshava
'''
from nxdrive.engine.workers import PollWorker
from datetime import timedelta
from nxdrive.logging_config import get_logger
import urllib2


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
        self._user_cache = dict()

    def _poll(self):
        '''
            Refresh first name and last name of all users
        '''
        log.trace("Refreshing Users table")
        try:
            # This method will retrieve the first 50 users for the current tenant (includes guest users also). This is re-using API meant for user search in DM UI
            self.fetch_all_users()
            # For remaining users we userid to user full name resolution done by 'api/v1/user/<userid>'
            # while True:
            to_refresh = self._engine._dao.get_next_users_to_resolve()
            for user in to_refresh:
                self.get_user_full_name(user.user_id)
        except Exception as ex:
            # Avoid crashing the thread if a poll fails
            log.exception(ex)
        log.trace("Completed refreshing Users table")

    def refresh_user(self, user_id):
        '''
            Retrieve user if not in the database 
        '''
        if (not user_id) or (user_id == "system"):
            return
        # If user_id is present in local cache, it is also present in database
        # so return
        if user_id in self._user_cache:
            return
        log.trace("user_id=%r not present in _user_cache" % user_id)
        # Retrieve the user_info from local database
        user_info = self._engine._dao.get_user_info(user_id)
        if not user_info:
            log.trace("user_id=%r not present in local database" % user_id)
            # If not present in local database, it is new user. Fetch from server
            user_info = self.get_user_full_name(user_id)
        log.trace("user_id=%r resolved to user_info=%r" % (user_id, dict(user_info)))
        # Update the local cache with user_info
        if user_info:
            self._user_cache[user_id] = user_info
        return

    def get_user_full_name(self, user_id):
        """
            Get the last contributor full name
        """
        try:
            rest_client = self._engine.get_rest_api_client()
            response = rest_client.get_user_full_name(user_id)
            if response and isinstance(response, dict) and \
                'properties' in response and isinstance(response['properties'], dict):
                properties = response['properties']
                firstName = properties.get('firstName')
                lastName = properties.get('lastName')
                self._engine._dao.insert_update_user_info(user_id, firstName, lastName)
        except urllib2.URLError as e:
            log.exception(e)
        return self._engine._dao.get_user_info(user_id)

    def fetch_all_users(self):
        '''
            Retrieve the userid - user name mapping of users in the current tenant
        '''
        try:
            remote_doc_client = self._engine.get_remote_doc_client()
            all_users = remote_doc_client.get_all_users()
            for user in all_users:
                if 'username' in user and 'firstName' in user and 'lastName' in user:
                    self._engine._dao.insert_update_user_info(user["username"], user['firstName'], user['lastName'])
        except Exception as e:
            log.exception(e)
        return
