'''
@author: Remi Cattiau
'''
from nxdrive.logging_config import get_logger
from nxdrive.engine.workers import Worker, ThreadInterrupt
from nxdrive.engine.blacklist_queue import BlacklistQueue
from nxdrive.engine.watcher.local_watcher import DriveFSEventHandler, normalize_event_filename
from nxdrive.engine.activity import Action
from nxdrive.client.local_client import LocalClient
from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_PREFIX
from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_SUFFIX
from nxdrive.client.common import safe_filename, NotFound
from nxdrive.utils import force_decode
import os
import sys
import urllib2
from time import sleep
import shutil
from PyQt4.QtCore import pyqtSignal
from Queue import Queue, Empty
log = get_logger(__name__)


class DriveEdit(Worker):
    localScanFinished = pyqtSignal()
    driveEditUploadCompleted = pyqtSignal()
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
        if type(folder) == str:
            folder = unicode(folder)
        self._folder = folder
        self._local_client = LocalClient(self._folder)
        self._upload_queue = Queue()
        self._error_queue = BlacklistQueue()
        self._stop = False

    def stop(self):
        super(DriveEdit, self).stop()
        self._stop = True

    def stop_client(self, reason):
        if self._stop:
            raise ThreadInterrupt

    def _cleanup(self):
        log.debug("Cleanup DriveEdit folder")
        shutil.rmtree(self._folder, ignore_errors=True)
        if not os.path.exists(self._folder):
            os.mkdir(self._folder)

    def _get_engine(self, url, user=None):
        if url.endswith('/'):
            url = url[:-1]
        for engine in self._manager.get_engines().values():
            bind = engine.get_binder()
            server_url = bind.server_url
            if server_url.endswith('/'):
                server_url = server_url[:-1]
            if server_url == url and (user is None or user == bind.username):
                return engine
        # Some backend are case insensitive
        if user is None:
            return None
        user = user.lower()
        for engine in self._manager.get_engines().values():
            bind = engine.get_binder()
            server_url = bind.server_url
            if server_url.endswith('/'):
                server_url = server_url[:-1]
            if server_url == url and user == bind.username.lower():
                return engine
        return None

    def _download_content(self, engine, remote_client, info, file_path, url=None):
        file_dir = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        file_out = os.path.join(file_dir, DOWNLOAD_TMP_FILE_PREFIX + file_name
                                + DOWNLOAD_TMP_FILE_SUFFIX)
        # Close to processor method - should try to refactor ?
        pair = engine.get_dao().get_valid_duplicate_file(info.digest)
        if pair:
            local_client = engine.get_local_client()
            shutil.copy(local_client._abspath(pair.local_path), file_out)
        else:
            if url is not None:
                remote_client.do_get(url, file_out=file_out, digest=info.digest, digest_algorithm=info.digest_algorithm)
            else:
                remote_client.get_blob(info.uid, file_out=file_out)
        return file_out

    def _prepare_edit(self, server_url, doc_id, filename, user=None, download_url=None):
        engine = self._get_engine(server_url, user=user)
        if engine is None:
            # TO_REVIEW Display an error message
            log.debug("No engine found for %s(%s)", server_url, doc_id)
            return
        # Get document info
        remote_client = engine.get_remote_doc_client()
        # Avoid any link with the engine, remote_doc are not cached so we can do that
        remote_client.check_suspended = self.stop_client
        info = remote_client.get_info(doc_id)

        # Create local structure
        dir_path = os.path.join(self._folder, doc_id)
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)

        log.trace('Raw filename: %r', filename)
        filename = safe_filename(urllib2.unquote(filename))
        log.trace('Unquoted filename = %r', filename)
        decoded_filename = force_decode(filename)
        if decoded_filename is None:
            decoded_filename = filename
        else:
            # Always use utf-8 encoding for xattr
            filename = decoded_filename.encode('utf-8')
        log.debug("Editing %r ('nxdriveeditname' xattr: %r)", decoded_filename, filename)
        file_path = os.path.join(dir_path, decoded_filename)

        # Download the file
        url = None
        if download_url is not None:
            url = server_url
            if not url.endswith('/'):
                url += '/'
            url += download_url
        tmp_file = self._download_content(engine, remote_client, info, file_path, url=url)
        if tmp_file is None:
            log.debug("Download failed")
            return
        # Set the remote_id
        dir_path = self._local_client.get_path(os.path.dirname(file_path))
        self._local_client.set_remote_id(dir_path, doc_id)
        self._local_client.set_remote_id(dir_path, server_url, "nxdriveedit")
        if user is not None:
            self._local_client.set_remote_id(dir_path, user, "nxdriveedituser")
        self._local_client.set_remote_id(dir_path, info.digest, "nxdriveeditdigest")
        self._local_client.set_remote_id(dir_path, filename, "nxdriveeditname")
        # Rename to final filename
        # Under Windows first need to delete target file if exists, otherwise will get a 183 WindowsError
        if sys.platform == 'win32' and os.path.exists(file_path):
            os.unlink(file_path)
        os.rename(tmp_file, file_path)

        return file_path

    def edit(self, server_url, doc_id, filename, user=None, download_url=None):
        # Download file
        file_path = self._prepare_edit(server_url, doc_id, filename, user=user, download_url=download_url)
        # Launch it
        if file_path is not None:
            self._manager.open_local_file(file_path)

    def _handle_queue(self):
        uploaded = False
        # Unqueue any errors
        item = self._error_queue.get()
        while (item is not None):
            self._upload_queue.put(item.get())
            item = self._error_queue.get()
        # Handle the upload queue
        while (not self._upload_queue.empty()):
            try:
                ref = self._upload_queue.get_nowait()
                log.trace('Handling DriveEdit queue ref: %r', ref)
            except Empty:
                break
            dir_path = os.path.dirname(ref)
            uid = self._local_client.get_remote_id(dir_path)
            server_url = self._local_client.get_remote_id(dir_path, "nxdriveedit")
            user = self._local_client.get_remote_id(dir_path, "nxdriveedituser")
            engine = self._get_engine(server_url, user=user)
            remote_client = engine.get_remote_doc_client()
            remote_client.check_suspended = self.stop_client
            digest = self._local_client.get_remote_id(dir_path, "nxdriveeditdigest")
            # Don't update if digest are the same
            info = self._local_client.get_info(ref)
            try:
                if info.get_digest() == digest:
                    continue
                # TO_REVIEW Should check if blob has changed ?
                # Update the document - should verify the hash - NXDRIVE-187
                log.debug('Uploading file %s for user %s', self._local_client._abspath(ref),
                          user)
                remote_client.stream_update(uid, self._local_client._abspath(ref), apply_versioning_policy=True)
            except ThreadInterrupt:
                raise
            except Exception as e:
                # Try again in 30s
                log.trace("Exception on drive edit: %r", e)
                self._error_queue.push(ref, ref)
                continue
            uploaded = True
        if uploaded:
            log.debug('Emitting driveEditUploadCompleted')
            self.driveEditUploadCompleted.emit()

    def _execute(self):
        try:
            self._watchdog_queue = Queue()
            self._action = Action("Clean up folder")
            self._cleanup()
            self._action = Action("Setup watchdog")
            self._setup_watchdog()
            self._end_action()
            while (1):
                self._interact()
                try:
                    self._handle_queue()
                except NotFound:
                    pass
                while (not self._watchdog_queue.empty()):
                    evt = self._watchdog_queue.get()
                    self.handle_watchdog_event(evt)
                sleep(0.01)
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
        log.debug("Handling watchdog event [%s] on %r", evt.event_type, evt.src_path)
        try:
            src_path = normalize_event_filename(evt.src_path)
            # Event on the folder by itself
            if os.path.isdir(src_path):
                return
            ref = self._local_client.get_path(src_path)
            file_name = os.path.basename(src_path)
            if self._local_client.is_temp_file(file_name):
                return
            queue = False
            if evt.event_type == 'modified' or evt.event_type == 'created':
                queue = True
            if evt.event_type == 'moved':
                ref = self._local_client.get_path(evt.dest_path)
                file_name = os.path.basename(evt.dest_path)
                queue = True
            dir_path = self._local_client.get_path(os.path.dirname(src_path))
            name = self._local_client.get_remote_id(dir_path, "nxdriveeditname")
            if name is None:
                return
            decoded_name = force_decode(name)
            if decoded_name is not None:
                name = decoded_name
            if name != file_name:
                return
            if queue:
                # ADD TO UPLOAD QUEUE
                self._upload_queue.put(ref)
                return
        except Exception as e:
            log.warn("Watchdog exception : %r" % e)
            log.exception(e)
        finally:
            self._end_action()
