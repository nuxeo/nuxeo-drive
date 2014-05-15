'''
Created on 9 mai 2014

@author: Remi Cattiau
'''
from PyQt4 import QtGui
import time
TIME_FORMAT_PATTERN = '%d %b %H:%M'
from nxdrive.updater import UPDATE_STATUS_UNAVAILABLE_SITE
from nxdrive.updater import UPDATE_STATUS_MISSING_INFO
from nxdrive.updater import UPDATE_STATUS_MISSING_VERSION
from nxdrive.updater import UPDATE_STATUS_UP_TO_DATE
from nxdrive.logging_config import get_logger

log = get_logger(__name__)

class SystrayMenu(QtGui.QMenu):
    '''
    classdocs
    '''
    def __init__(self,application,server_bindings):
        '''
        Constructor
        '''
        super(SystrayMenu,self).__init__()
        self.update_action = None

        self.application = application
        self.binding_menu_actions = {}
        self.global_menu_actions = {}
        self.create_menu(server_bindings)
        
    
    def _insert_last_ended_sync_action(self, last_ended_sync_date,
                                       before_action):
        last_ended_sync_action = QtGui.QAction(self)
        last_ended_sync_action.setEnabled(False)
        self._set_last_ended_sync(last_ended_sync_action, last_ended_sync_date)
        self.insertAction(before_action,last_ended_sync_action)
        return last_ended_sync_action

    def _set_pending_status(self, status_action, binding_info, server_binding):
        status_message = binding_info.get_status_message()
        # Need to re-fetch authentication token when expired
        if server_binding.has_invalid_credentials():
            status_message += " (credentials update required)"
        status_action.setText(status_message)

    def _set_last_ended_sync(self, last_ended_sync_action,
                             last_ended_sync_date):
        last_ended_sync_message = "Last synchronized: %s" % (
                                    time.strftime(TIME_FORMAT_PATTERN,
                                    time.localtime(last_ended_sync_date)))
        last_ended_sync_action.setText(last_ended_sync_message)
    
    def update_menu(self, server_bindings):
            # TODO: i18n action labels
        # Global actions
        quit_action = self.global_menu_actions.get('quit')

        # Create menu if server_bindings has changed
        if server_bindings:
            if self.is_bind == False:
                self.remove_default_menu()
                self.create_bind_menu(server_bindings)
            self.update_bind_menu(server_bindings)
            return
        if not server_bindings and self.is_bind == True:
            self.create_default_menu()
            self.remove_bind_menu()
            # Default menu has no update
            return
        
        # Update Quit button according to state
        if self.application.state == 'stopping':
            quit_action.setText('Quitting...')
            # Disable quit and suspend_resume actions when quitting
            quit_action.setEnabled(False)
            
    def create_bind_menu(self,server_bindings):
        # Create the bind menu composed by a global suspend action
        # And a section per server
        self.is_bind = True
        suspend_resume_action = QtGui.QAction(
                                        "Suspend synchronization",
                                        self,
                                        triggered=self.application.suspend_resume)
        self.insertAction(self.settings_action, suspend_resume_action)
        self.global_menu_actions['suspend_resume'] = (
                                                    suspend_resume_action)
        binding_separator = QtGui.QAction(self)
        binding_separator.setSeparator(True)
        self.insertAction(self.settings_action,binding_separator)
        self.global_menu_actions['suspend_resume_sep'] = (
                                                    binding_separator)
        
        for sb in server_bindings:
            self.create_bind_server_menu(sb)
        

    def remove_default_menu(self):
        # Remove global status action from menu and from
        # global menu action cache
        global_status_action = self.global_menu_actions.get('global_status')
        global_status_sep = self.global_menu_actions.get('global_status_sep')
        if global_status_action and global_status_sep is not None:
            self.removeAction(global_status_action)
            self.removeAction(global_status_sep)
            del self.global_menu_actions['global_status']
            del self.global_menu_actions['global_status_sep']
    
    def create_default_menu(self):
        # Default menu when no binding is found
        global_status_action = QtGui.QAction(
                                            "Waiting for server registration",
                                            self)
        global_status_action.setEnabled(False)
        self.insertAction(self.settings_action,global_status_action)
        self.global_menu_actions['global_status'] = (
                                                        global_status_action)
        global_status_sep = QtGui.QAction(self)
        global_status_sep.setSeparator(True)
        self.insertAction(self.settings_action,global_status_sep)
        self.global_menu_actions['global_status_sep'] = (
                                                        global_status_sep)
        
    def create_menu(self, server_bindings):
        # Add settings
        self.settings_action = QtGui.QAction("Settings",
                                        self,
                                        triggered=self.application.settings)
        self.addAction(self.settings_action)
        
        
        # Quit
        self.addSeparator()
        self.quit_action = QtGui.QAction("Quit", self,
                                        triggered=self.application.action_quit)
        self.addAction(self.quit_action)
        self.auto_update_menu()
        # Create the menu as the client is bind to servers
        self.is_bind = False
        if server_bindings:
            self.create_bind_menu(server_bindings)
        else:
            self.create_default_menu()
            
    def remove_bind_menu(self):
        global_status_action = self.global_menu_actions.get('suspend_resume')
        global_status_sep = self.global_menu_actions.get('suspend_resume_sep')
        if global_status_action and global_status_sep is not None:
            self.removeAction(global_status_action)
            self.removeAction(global_status_sep)
            del self.global_menu_actions['suspend_resume']
            del self.global_menu_actions['suspend_resume_sep']
        for bind_action in self.binding_menu_actions.values():
            self.removeAction(bind_action)
            del bind_action
        return
    
    def create_bind_server_menu(self,server_binding):
        binding_info = self.application.get_binding_info(server_binding)
        last_ended_sync_date = server_binding.last_ended_sync_date
        sb_actions = {}
        # Separator
        binding_separator = QtGui.QAction(self)
        binding_separator.setSeparator(True)
        self.insertAction(self.settings_action,binding_separator)
        sb_actions['separator'] = binding_separator

        # Link to open the server binding folder
        open_folder_msg = ("Open %s folder"
                                   % binding_info.short_name)
        open_folder = (lambda folder_path=binding_info.folder_path:
                               self.controller.open_local_file(
                                                            folder_path))
        open_folder_action = QtGui.QAction(open_folder_msg,
                                                   self)
        open_folder_action.triggered.connect(open_folder)
        self.insertAction(binding_separator,open_folder_action)
        sb_actions['open_folder'] = open_folder_action

        # Link to Nuxeo server
        server_link_msg = "Browse Nuxeo server"
        open_server_link = (
                        lambda server_link=binding_info.server_link:
                        self.controller.open_local_file(server_link))
        server_link_action = QtGui.QAction(server_link_msg,self)
        server_link_action.triggered.connect(open_server_link)
        self.insertAction(binding_separator,server_link_action)
        sb_actions['server_link'] = server_link_action

        # Pending status
        status_action = QtGui.QAction(self)
        status_action.setEnabled(False)
        self._set_pending_status(status_action, binding_info, server_binding)
        self.insertAction(binding_separator,status_action)
        sb_actions['pending_status'] = status_action

        # Last synchronization date
        if last_ended_sync_date is not  None:
            last_ended_sync_action = (
                                        self._insert_last_ended_sync_action(
                                            last_ended_sync_date,
                                            binding_separator))
            sb_actions['last_ended_sync'] = last_ended_sync_action

        # Cache server binding menu actions
        self.binding_menu_actions[server_binding.local_folder] = sb_actions
        
    def update_bind_server_menu(self,server_binding,sb_actions):
        binding_info = self.application.get_binding_info(server_binding)
        last_ended_sync_date = server_binding.last_ended_sync_date
        # Update pending status
        status_action = sb_actions['pending_status']
        self._set_pending_status(status_action, binding_info, server_binding)

        # Update last synchronization date
        last_ended_sync_action = sb_actions.get('last_ended_sync')
        if last_ended_sync_action is None:
            if last_ended_sync_date is not None:
                last_ended_sync_action = (
                                        self._insert_last_ended_sync_action(
                                            last_ended_sync_date,
                                            sb_actions['separator']))
                sb_actions['last_ended_sync'] = last_ended_sync_action
            else:
                if last_ended_sync_date is not None:
                    self._set_last_ended_sync(last_ended_sync_action,last_ended_sync_date)
    
    def remove_bind_servers(self,obsolete_binding_local_folders):
        # Remove obsolete binding actions from menu and from
        # binding menu action cache
        for local_folder in obsolete_binding_local_folders:
            sb_actions = self.binding_menu_actions[local_folder]
            if sb_actions is not None:
                for action_id in sb_actions.keys():
                    self.removeAction(sb_actions[action_id])
                    del sb_actions[action_id]
                del self.binding_menu_actions[local_folder]
       
    def update_bind_menu(self,server_bindings):
        obsolete_binding_local_folders = self.binding_menu_actions.keys()
        suspend_resume_action = self.global_menu_actions.get('suspend_resume')
        quit_action = self.global_menu_actions.get('quit')
        
        # Suspend / resume
        if self.application.state == 'suspending':
            suspend_resume_action.setText(
                                        'Suspending synchronization...')
            # Disable suspend_resume and quit actions when suspending
            suspend_resume_action.setEnabled(False)
            quit_action.setEnabled(False)
        elif self.application.state == 'paused':
            suspend_resume_action.setText('Resume synchronization')
            # Enable suspend_resume and quit actions when paused
            suspend_resume_action.setEnabled(True)
            quit_action.setEnabled(True)
        else:
            suspend_resume_action.setText('Suspend synchronization')
            
        # Add or update server binding actions
        for sb in server_bindings:
            if sb.local_folder in obsolete_binding_local_folders:
                obsolete_binding_local_folders.remove(sb.local_folder)
            sb_actions = self.binding_menu_actions.get(sb.local_folder)
            if sb_actions is None:
                self.create_bind_server_menu(sb)
            else:
                self.update_bind_server_menu(sb,sb_actions)

        # Remove old binding
        self.remove_bind_servers(obsolete_binding_local_folders)
        
        # Handle the auto-update menu
        self.auto_update_menu()        
        # Disable resume when stopping        
        if self.application.state == 'stopping':
            suspend_resume_action.setEnabled(False)
            
            
    ### AUTO UPDATE
    def auto_update_menu(self):
        # Update
        if self.update_action is None:
            if (self.application.update_status is not None and self.application.updater is not None
                and self.application.update_status != UPDATE_STATUS_UP_TO_DATE):
                update_label = self.application.updater.get_update_label(
                                                            self.update_status)
                self.update_action = QtGui.QAction(update_label,
                                              self.tray_icon_menu,
                                              triggered=self.action_update)
                if self.application.update_status in [UPDATE_STATUS_UNAVAILABLE_SITE,
                                          UPDATE_STATUS_MISSING_INFO,
                                          UPDATE_STATUS_MISSING_VERSION]:
                    self.update_action.setEnabled(False)
                self.insertAction(self.quit_action,self.update_action)
                self.global_menu_actions['update'] = self.update_action
        else:
            if (self.application.update_status is not None
                and self.application.update_status != UPDATE_STATUS_UP_TO_DATE):
                # Update update action label
                update_label = self.application.updater.get_update_label(
                                                            self.update_status)
                self.update_action.setText(update_label)
                if self.application.update_status in [UPDATE_STATUS_UNAVAILABLE_SITE,
                                          UPDATE_STATUS_MISSING_INFO,
                                          UPDATE_STATUS_MISSING_VERSION]:
                    self.update_action.setEnabled(False)
                else:
                    self.update_action.setEnabled(True)
            else:
                # Remove update action from menu and from global menu action
                # cache
                self.tray_icon_menu.removeAction(self.update_action)
                del self.global_menu_actions['update']
