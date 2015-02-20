'''
@author: Remi Cattiau
'''
from nxdrive.logging_config import get_logger
from nxdrive.engine.workers import Worker, ThreadInterrupt
from nxdrive.engine.watcher.local_watcher import DriveFSEventHandler, normalize_event_filename
from nxdrive.engine.activity import Action
from nxdrive.client.local_client import LocalClient
from nxdrive.client.common import safe_filename
import os
from time import sleep
import shutil
from PyQt4.QtCore import pyqtSignal
from Queue import Queue, Empty
log = get_logger(__name__)


class DriveEdit(Worker):
    localScanFinished = pyqtSignal()
    '''
    classdocs
    '''
    def __init__(self, manager, folder):
        '''
        Constructor
        '''
        super(DriveEdit, self).__init__()
        self._manager = manager
        self._thread.started.connect(self.run)
        self._event_handler = None
        self._metrics = dict()
        self._metrics['edit_files'] = 0
        self._observer = None
        self._folder = folder
        self._local_client = LocalClient(self._folder)
        self._upload_queue = Queue()

    def _cleanup(self):
        log.debug("Cleanup DriveEdit folder")
        shutil.rmtree(self._folder, True)
        if not os.path.exists(self._folder):
            os.mkdir(self._folder)

    def _get_engine(self, url, user):
        for engine in self._manager.get_engines().values():
            bind = engine.get_binder()
            if bind.server_url == url and (user is None or user == bind.username):
                return engine

    def _download_content(self, engine, remote_client, info, file_path):
        # Close to processor method - should try to refactor ?
        pair = engine.get_dao().get_valid_duplicate_file(info.digest)
        if pair:
            from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_PREFIX
            from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_SUFFIX
            local_client = engine.get_local_client()
            file_dir = os.path.dirname(file_path)
            file_name = os.path.basename(file_path)
            file_out = os.path.join(file_dir, DOWNLOAD_TMP_FILE_PREFIX + file_name
                                + DOWNLOAD_TMP_FILE_SUFFIX)
            shutil.copy(local_client._abspath(pair.local_path), file_out)
            return file_out
        tmp_file = remote_client.stream_content(
                                info.remote_ref, file_path,
                                parent_fs_item_id=None,
                                fs_item_info=info)
        return tmp_file

    def edit(self, server_url, repo, doc_id, filename, user=None):
        engine = self._get_engine(server_url, user)
        if engine is None:
            # TO_REVIEW Display an error message
            return
        # Get document info
        remote_client = engine.get_remote_client()
        info = remote_client.get_info(doc_id)

        # Create local structure
        dir_path = os.path.join(self._folder, doc_id)
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)
        file_path = os.path.join(dir_path, safe_filename(info.name))

        # Download the file
        tmp_file = self._download_content(engine, remote_client, info, file_path)
        # Set the remote_id
        ref = self._local_client.get_path(tmp_file)
        self._local_client.set_remote_id(ref, doc_id)
        self._local_client.set_remote_id(ref, server_url, "nxdriveedit")
        # Rename to final filename
        os.rename(tmp_file, file_path)

        # Launch it
        self._manager.open_local_file(file_path)

    def _handle_queue(self):
        while (not self._upload_queue.empty()):
            try:
                ref = self._upload_queue.get_nowait()
            except Empty:
                return
            uid = self._local_client.get_remote_id(ref)
            server_url = self._local_client.get_remote_id(ref, "nxdriveedit")
            engine = self._get_engine(server_url)
            remote_client = engine.get_remote_client()
            # Update the document - should verify the hash - NXDRIVE-187
            remote_client.stream_update(uid, self._local_client._abspath(ref))

    def _execute(self):
        try:
            self._action = Action("Clean up folder")
            self._cleanup()
            self._action = Action("Setup watchdog")
            self._setup_watchdog()
            self._end_action()
            while (1):
                self._interact()
                self._handle_queue()
                sleep(1)
        except ThreadInterrupt:
            raise
        finally:
            self._stop_watchdog()

    def get_metrics(self):
        metrics = super(DriveEdit, self).get_metrics()
        if self._event_handler is not None:
            metrics['fs_events'] = self._event_handler.counter
        return dict(metrics.items() + self._metrics.items())

    def _setup_watchdog(self):
        from watchdog.observers import Observer
        log.debug("Watching FS modification on : %s", self._folder)
        self._event_handler = DriveFSEventHandler(self)
        self._observer = Observer()
        self._observer.schedule(self._event_handler, self._folder, recursive=True)
        self._observer.start()

    def _stop_watchdog(self, raise_on_error=True):
        if self._observer is None:
            return
        log.info("Stopping FS Observer thread")
        try:
            self._observer.stop()
        except Exception as e:
            log.warn("Can't stop FS observer : %r", e)
        # Wait for all observers to stop
        try:
            self._observer.join()
        except Exception as e:
            log.warn("Can't join FS observer : %r", e)
        # Delete all observers
        self._observer = None

    def handle_watchdog_event(self, evt):
        self._action = Action("Handle watchdog event")
        log.debug("handle_watchdog_event %s on %s", evt.event_type, evt.src_path)
        try:
            src_path = normalize_event_filename(evt.src_path)
            # Event on the folder by itself
            if os.path.isdir(src_path):
                return
            rel_path = self._local_client.get_path(src_path)
            file_name = os.path.basename(src_path)
            parent_path = os.path.dirname(src_path)
            parent_rel_path = self._local_client.get_path(parent_path)
            # Dont care about ignored file, unless it is moved
            if (self._local_client.is_ignored(parent_rel_path, file_name)
                  and evt.event_type != 'moved'):
                return
            if self.client.is_temp_file(file_name):
                return
            if evt.event_type == 'modified':
                # ADD TO UPLOAD QUEUE
                self._upload_queue.put(rel_path)
                return
        except Exception as e:
            log.warn("Watchdog exception : %r" % e)
            log.exception(e)
        finally:
            self._end_action()
