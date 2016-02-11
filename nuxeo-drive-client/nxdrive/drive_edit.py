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
from nxdrive.utils import guess_digest_algorithm, current_milli_time
from nxdrive.osi import parse_protocol_url
import os
import sys
import urllib2
from time import sleep
import shutil
from PyQt4.QtCore import pyqtSignal, pyqtSlot
from Queue import Queue, Empty
log = get_logger(__name__)
WindowsError = None
try:
    from exceptions import WindowsError
except ImportError:
    pass  # this will never be raised under unix


class DriveEdit(Worker):
    localScanFinished = pyqtSignal()
    driveEditUploadCompleted = pyqtSignal()
    openDocument = pyqtSignal(object)
    editDocument = pyqtSignal(object)
    driveEditLockError = pyqtSignal(str, str, str)
    driveEditConflict = pyqtSignal(str, str, str)

    '''
    classdocs
    '''
    def __init__(self, manager, folder, url):
        '''
        Constructor
        '''
        super(DriveEdit, self).__init__()
        self._manager = manager
        self._url = url
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
        self._lock_queue = Queue()
        self._error_queue = BlacklistQueue()
        self._stop = False
        self._manager.get_autolock_service().orphanLocks.connect(self._autolock_orphans)
        self._last_action_timing = -1

    @pyqtSlot(object)
    def _autolock_orphans(self, locks):
        log.trace("Orphans lock: %r", locks)
        for lock in locks:
            if lock.path.startswith(self._folder):
                log.debug("Should unlock: %s", lock.path)
                ref = self._local_client.get_path(lock.path)
                self._lock_queue.put((ref, 'unlock_orphan'))

    def autolock_lock(self, src_path):
        ref = self._local_client.get_path(src_path)
        self._lock_queue.put((ref, 'lock'))

    def autolock_unlock(self, src_path):
        ref = self._local_client.get_path(src_path)
        self._lock_queue.put((ref, 'unlock'))

    def stop(self):
        super(DriveEdit, self).stop()
        self._stop = True

    def stop_client(self, reason):
        if self._stop:
            raise ThreadInterrupt

    def handle_url(self, url=None):
        if url is None:
            url = self._url
        if url is None:
            return
        log.debug("DriveEdit load: '%r'", url)
        try:
            info = parse_protocol_url(str(url))
        except UnicodeEncodeError:
            # Firefox seems to be different on the encoding part
            info = parse_protocol_url(unicode(url))
        if info is None:
            return
        # Handle backward compatibility
        if info.get('item_id') is not None:
            self.edit(info['server_url'], info['item_id'])
        else:
            self.edit(info['server_url'], info['doc_id'], filename=info['filename'],
                      user=info['user'], download_url=info['download_url'])

    def _cleanup(self):
        log.debug("Cleanup DriveEdit folder")
        # Should unlock any remaining doc that has not been unlocked or ask
        if self._local_client.exists('/'):
            for child in self._local_client.get_children_info('/'):
                if self._local_client.get_remote_id(child.path, "nxdriveeditlock") is not None:
                    continue
                # Place for handle reopened of interrupted Edit
                shutil.rmtree(self._local_client._abspath(child.path), ignore_errors=True)
        if not os.path.exists(self._folder):
            os.mkdir(self._folder)

    def _get_engine(self, url, user=None):
        if url is None:
            return None
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
            existing_file_path = local_client._abspath(pair.local_path)
            log.debug('Local file matches remote digest %r, copying it from %r', info.digest, existing_file_path)
            shutil.copy(existing_file_path, file_out)
            if pair.is_readonly():
                log.debug('Unsetting readonly flag on copied file %r', file_out)
                from nxdrive.client.common import BaseClient
                BaseClient.unset_path_readonly(file_out)
        else:
            log.debug('Downloading file %r', info.filename)
            if url is not None:
                remote_client.do_get(url, file_out=file_out, digest=info.digest, digest_algorithm=info.digest_algorithm)
            else:
                remote_client.get_blob(info, file_out=file_out)
        return file_out

    def _display_modal(self, message, values=None):
        from nxdrive.wui.application import SimpleApplication
        from nxdrive.wui.modal import WebModal
        app = SimpleApplication(self._manager, None, {})
        dialog = WebModal(app, app.translate(message, values))
        dialog.add_button("OK", app.translate("OK"))
        dialog.show()
        app.exec_()

    def _prepare_edit(self, server_url, doc_id, user=None, download_url=None):
        start_time = current_milli_time()
        engine = self._get_engine(server_url, user=user)
        if engine is None:
            values = dict()
            values['user'] = user
            values['server'] = server_url
            log.warn("No engine found for %s(%s)", server_url, doc_id)
            self._display_modal("DIRECT_EDIT_CANT_FIND_ENGINE", values)
            return
        # Get document info
        remote_client = engine.get_remote_doc_client()
        # Avoid any link with the engine, remote_doc are not cached so we can do that
        remote_client.check_suspended = self.stop_client
        info = remote_client.get_info(doc_id)
        filename = info.filename

        # Create local structure
        dir_path = os.path.join(self._folder, doc_id)
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)

        log.debug("Editing %r", filename)
        file_path = os.path.join(dir_path, filename)

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
        if info.digest is not None:
            self._local_client.set_remote_id(dir_path, info.digest, "nxdriveeditdigest")
            # Set digest algorithm if not sent by the server
            digest_algorithm = info.digest_algorithm
            if digest_algorithm is None:
                digest_algorithm = guess_digest_algorithm(info.digest)
            self._local_client.set_remote_id(dir_path, digest_algorithm, "nxdriveeditdigestalgorithm")
        self._local_client.set_remote_id(dir_path, filename, "nxdriveeditname")
        # Rename to final filename
        # Under Windows first need to delete target file if exists, otherwise will get a 183 WindowsError
        if sys.platform == 'win32' and os.path.exists(file_path):
            os.unlink(file_path)
        os.rename(tmp_file, file_path)
        self._last_action_timing = current_milli_time() - start_time
        self.openDocument.emit(info)
        return file_path

    def edit(self, server_url, doc_id, filename=None, user=None, download_url=None):
        try:
            # Handle backward compatibility
            if '#' in doc_id:
                engine = self._get_engine(server_url)
                if engine is None:
                    log.warn("No engine found for %s, cannot edit file with remote ref %s", server_url, doc_id)
                    return
                self._manager.edit(engine, doc_id)
            else:
                # Download file
                file_path = self._prepare_edit(server_url, doc_id, user=user, download_url=download_url)
                # Launch it
                if file_path is not None:
                    self._manager.open_local_file(file_path)
        except WindowsError as e:
            if e.errno == 13:
                # open file anyway
                if e.filename is not None:
                    self._manager.open_local_file(e.filename)
            else:
                raise e

    def _extract_edit_info(self, ref):
        dir_path = os.path.dirname(ref)
        uid = self._local_client.get_remote_id(dir_path)
        server_url = self._local_client.get_remote_id(dir_path, "nxdriveedit")
        user = self._local_client.get_remote_id(dir_path, "nxdriveedituser")
        engine = self._get_engine(server_url, user=user)
        if engine is None:
            raise NotFound()
        remote_client = engine.get_remote_doc_client()
        remote_client.check_suspended = self.stop_client
        digest_algorithm = self._local_client.get_remote_id(dir_path, "nxdriveeditdigestalgorithm")
        digest = self._local_client.get_remote_id(dir_path, "nxdriveeditdigest")
        return uid, engine, remote_client, digest_algorithm, digest

    def force_update(self, ref, digest):
        dir_path = os.path.dirname(ref)
        self._local_client.set_remote_id(dir_path, unicode(digest), "nxdriveeditdigest")
        self._upload_queue.put(ref)

    def _handle_queues(self):
        uploaded = False
        # Lock any documents
        while (not self._lock_queue.empty()):
            try:
                item = self._lock_queue.get_nowait()
                ref = item[0]
                log.trace('Handling DriveEdit lock queue ref: %r', ref)
            except Empty:
                break
            uid = ""
            try:
                dir_path = os.path.dirname(ref)
                uid, engine, remote_client, _, _ = self._extract_edit_info(ref)
                if item[1] == 'lock':
                    remote_client.lock(uid)
                    self._local_client.set_remote_id(dir_path, "1", "nxdriveeditlock")
                    # Emit the lock signal only when the lock is really set
                    self._manager.get_autolock_service().documentLocked.emit(os.path.basename(ref))
                else:
                    remote_client.unlock(uid)
                    if item[1] == 'unlock_orphan':
                        path = self._local_client._abspath(ref)
                        log.trace("Remove orphan: %s", path)
                        self._manager.get_autolock_service().orphan_unlocked(path)
                        # Clean the folder
                        shutil.rmtree(self._local_client._abspath(path), ignore_errors=True)
                    self._local_client.remove_remote_id(dir_path, "nxdriveeditlock")
                    # Emit the signal only when the unlock is done - might want to avoid the call on orphan
                    self._manager.get_autolock_service().documentUnlocked.emit(os.path.basename(ref))
            except Exception as e:
                # Try again in 30s
                log.debug("Can't %s document '%s': %r", item[1], ref, e, exc_info=True)
                self.driveEditLockError.emit(item[1], os.path.basename(ref), uid)
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
            uid,  engine, remote_client, digest_algorithm, digest = self._extract_edit_info(ref)
            # Don't update if digest are the same
            info = self._local_client.get_info(ref)
            try:
                current_digest = info.get_digest(digest_func=digest_algorithm)
                if current_digest == digest:
                    continue
                start_time = current_milli_time()
                log.trace("Local digest: %s is different from the recorded one: %s - modification detected for %r",
                          current_digest, digest, ref)
                # TO_REVIEW Should check if server-side blob has changed ?
                # Update the document - should verify the remote hash - NXDRIVE-187
                remote_info = remote_client.get_info(uid)
                if remote_info.digest != digest:
                    # Conflict detect
                    log.trace("Remote digest: %s is different from the recorded one: %s - conflict detected for %r",
                              remote_info.digest, digest, ref)
                    self.driveEditConflict.emit(os.path.basename(ref), ref, remote_info.digest)
                    continue
                log.debug('Uploading file %s', self._local_client._abspath(ref))
                remote_client.stream_update(uid, self._local_client._abspath(ref), apply_versioning_policy=True)
                # Update hash value
                dir_path = os.path.dirname(ref)
                self._local_client.set_remote_id(dir_path, current_digest, 'nxdriveeditdigest')
                self._last_action_timing = current_milli_time() - start_time
                self.editDocument.emit(remote_info)
            except ThreadInterrupt:
                raise
            except Exception as e:
                # Try again in 30s
                log.trace("Exception on drive edit: %r", e, exc_info=True)
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
            # Load the target url if Drive was not launched before
            self.handle_url()
            while (1):
                self._interact()
                try:
                    self._handle_queues()
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
        metrics['last_action_timing'] = self._last_action_timing
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

    def is_lock_file(self, name):
        return False and ((name.startswith("~$") # Office lock file
                or name.startswith(".~lock."))) # Libre/OpenOffice lock file

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
            if self.is_lock_file(file_name) and self._manager.get_drive_edit_auto_lock():
                if evt.event_type == 'created':
                    self._lock_queue.put((ref, 'lock'))
                elif evt.event_type == 'deleted':
                    self._lock_queue.put((ref, 'unlock'))
                return
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
            if name != file_name:
                return
            if self._manager.get_drive_edit_auto_lock() and self._local_client.get_remote_id(dir_path, "nxdriveeditlock") != "1":
                self._manager.get_autolock_service().set_autolock(src_path, self)
            if queue:
                # ADD TO UPLOAD QUEUE
                self._upload_queue.put(ref)
                return
        except Exception as e:
            log.warn("Watchdog exception : %r", e, exc_info=True)
        finally:
            self._end_action()
