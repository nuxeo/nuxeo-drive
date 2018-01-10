# coding: utf-8
import os
import shutil
import sys
from Queue import Empty, Queue
from logging import getLogger
from time import sleep

from PyQt4.QtCore import pyqtSignal, pyqtSlot

from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_PREFIX, \
    DOWNLOAD_TMP_FILE_SUFFIX
from nxdrive.client.common import BaseClient, NotFound
from nxdrive.client.local_client import LocalClient
from nxdrive.engine.activity import Action
from nxdrive.engine.blacklist_queue import BlacklistQueue
from nxdrive.engine.watcher.local_watcher import DriveFSEventHandler
from nxdrive.engine.workers import ThreadInterrupt, Worker
from nxdrive.osi import parse_protocol_url
from nxdrive.utils import current_milli_time, guess_digest_algorithm, \
    normalize_event_filename
from nxdrive.wui.application import SimpleApplication
from nxdrive.wui.modal import WebModal

log = getLogger(__name__)


class DirectEdit(Worker):
    localScanFinished = pyqtSignal()
    directEditUploadCompleted = pyqtSignal()
    openDocument = pyqtSignal(object)
    editDocument = pyqtSignal(object)
    directEditLockError = pyqtSignal(str, str, str)
    directEditConflict = pyqtSignal(str, str, str)
    directEditReadonly = pyqtSignal(object)
    directEditLocked = pyqtSignal(object, object, object)

    def __init__(self, manager, folder, url):
        super(DirectEdit, self).__init__()
        self._test = False
        self._manager = manager
        self._url = url
        self._thread.started.connect(self.run)
        self._event_handler = None
        self._metrics = dict()
        self._metrics['edit_files'] = 0
        self._observer = None
        if isinstance(folder, bytes):
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
                if not os.path.exists(lock.path):
                    self._manager.get_autolock_service().orphan_unlocked(lock.path)
                    continue
                ref = self._local_client.get_path(lock.path)
                self._lock_queue.put((ref, 'unlock_orphan'))

    def autolock_lock(self, src_path):
        ref = self._local_client.get_path(src_path)
        self._lock_queue.put((ref, 'lock'))

    def autolock_unlock(self, src_path):
        ref = self._local_client.get_path(src_path)
        self._lock_queue.put((ref, 'unlock'))

    def start(self):
        self._stop = False
        super(DirectEdit, self).start()

    def stop(self):
        super(DirectEdit, self).stop()
        self._stop = True

    def stop_client(self, _):
        if self._stop:
            raise ThreadInterrupt

    def handle_url(self, url=None):
        if url is None:
            url = self._url
        if url is None:
            return
        log.debug("DirectEdit load: '%r'", url)
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
            self.edit(info['server_url'], info['doc_id'], user=info['user'],
                      download_url=info['download_url'])

    def _cleanup(self):
        log.debug("Cleanup DirectEdit folder")
        # Should unlock any remaining doc that has not been unlocked or ask
        if self._local_client.exists('/'):
            for child in self._local_client.get_children_info('/'):
                if self._local_client.get_remote_id(child.path, "nxdirecteditlock") is not None:
                    continue
                children = self._local_client.get_children_info(child.path)
                if len(children) > 1:
                    log.warning('Cannot clean this document: %s', child.path)
                    continue
                if not children:
                    # Cleaning the folder it is empty
                    shutil.rmtree(self._local_client.abspath(child.path),
                                  ignore_errors=True)
                    continue
                ref = children[0].path
                try:
                    _,  _, _, digest_algorithm, digest = self._extract_edit_info(ref)
                except NotFound:
                    # Engine is not known anymore
                    shutil.rmtree(self._local_client.abspath(child.path),
                                  ignore_errors=True)
                    continue
                try:
                    # Don't update if digest are the same
                    info = self._local_client.get_info(ref)
                    current_digest = info.get_digest(digest_func=digest_algorithm)
                    if current_digest != digest:
                        log.warning('Document has been modified and '
                                    'not synchronized, readd to upload queue')
                        self._upload_queue.put(ref)
                        continue
                except Exception as e:
                    log.debug(e)
                    continue
                # Place for handle reopened of interrupted Edit
                shutil.rmtree(self._local_client.abspath(child.path),
                              ignore_errors=True)
        if not os.path.exists(self._folder):
            os.mkdir(self._folder)

    def _get_engine(self, url, user=None):
        if url is None:
            return None
        if url.endswith('/'):
            url = url[:-1]
        # Simplify port if possible
        if url.startswith('http:') and ':80/' in url:
            url = url.replace(':80/', '/')
        if url.startswith('https:') and ':443/' in url:
            url = url.replace(':443/', '/')
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
            # Simplify port if possible
            if server_url.startswith('http:') and ':80/' in server_url:
                server_url = server_url.replace(':80/', '/')
            if server_url.startswith('https:') and ':443/' in server_url:
                server_url = server_url.replace(':443/', '/')
            if server_url.endswith('/'):
                server_url = server_url[:-1]
            if server_url == url and user == bind.username.lower():
                return engine
        return None

    @staticmethod
    def _download_content(engine, remote_client, info, file_path, url=None):
        file_dir = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        file_out = os.path.join(file_dir, DOWNLOAD_TMP_FILE_PREFIX + file_name
                                + DOWNLOAD_TMP_FILE_SUFFIX)
        # Close to processor method - should try to refactor ?
        pair = engine.get_dao().get_valid_duplicate_file(info.digest)
        if pair:
            local_client = engine.get_local_client()
            existing_file_path = local_client.abspath(pair.local_path)
            log.debug('Local file matches remote digest %r, copying it from %r', info.digest, existing_file_path)
            shutil.copy(existing_file_path, file_out)
            if pair.is_readonly():
                log.debug('Unsetting readonly flag on copied file %r', file_out)
                BaseClient.unset_path_readonly(file_out)
        else:
            log.debug('Downloading file %r', info.filename)
            if url is not None:
                remote_client.do_get(url, file_out=file_out,
                                     digest=info.digest,
                                     digest_algorithm=info.digest_algorithm)
            else:
                remote_client.get_blob(info, file_out=file_out)
        return file_out

    def _display_modal(self, message, values=None):
        app = SimpleApplication(self._manager)
        dialog = WebModal(app, app.translate(message, values))
        dialog.add_button("OK", app.translate("OK"))
        dialog.show()
        app.exec_()

    def _prepare_edit(self, server_url, doc_id, user=None, download_url=None):
        start_time = current_milli_time()
        engine = self._get_engine(server_url, user=user)
        if engine is None:
            values = dict()
            values['user'] = str(user)
            values['server'] = server_url
            log.warning('No engine found for server_url=%s, user=%s, doc_id=%s',
                        server_url, user, doc_id)
            self._display_modal('DIRECT_EDIT_CANT_FIND_ENGINE', values)
            return None
        # Get document info
        remote_client = engine.get_remote_doc_client()
        # Avoid any link with the engine, remote_doc are not cached so we can do that
        remote_client.check_suspended = self.stop_client
        doc = remote_client.fetch(
            doc_id,
            extra_headers={'fetch-document': 'lock'},
            enrichers=['permissions'],
        )
        info = remote_client.doc_to_info(doc, fetch_parent_uid=False)
        if info.lock_owner is not None and info.lock_owner != engine.remote_user:
            log.debug("Doc %s was locked by %s on %s, won't download it for edit", info.name, info.lock_owner,
                      info.lock_created)
            self.directEditLocked.emit(info.name, info.lock_owner, info.lock_created)
            return None
        if info.permissions is not None and 'Write' not in info.permissions:
            log.debug("Doc %s is readonly for %s, won't download it for edit", info.name, user)
            self.directEditReadonly.emit(info.name)
            return None

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
            return None
        # Set the remote_id
        dir_path = self._local_client.get_path(os.path.dirname(file_path))
        self._local_client.set_remote_id(dir_path, doc_id)
        self._local_client.set_remote_id(dir_path, server_url, "nxdirectedit")
        if user is not None:
            self._local_client.set_remote_id(dir_path, user, "nxdirectedituser")
        if info.digest is not None:
            self._local_client.set_remote_id(dir_path, info.digest, "nxdirecteditdigest")
            # Set digest algorithm if not sent by the server
            digest_algorithm = info.digest_algorithm
            if digest_algorithm is None:
                digest_algorithm = guess_digest_algorithm(info.digest)
            self._local_client.set_remote_id(dir_path, digest_algorithm, "nxdirecteditdigestalgorithm")
        self._local_client.set_remote_id(dir_path, filename, "nxdirecteditname")
        # Rename to final filename
        # Under Windows first need to delete target file if exists, otherwise will get a 183 WindowsError
        if sys.platform == 'win32' and os.path.exists(file_path):
            os.unlink(file_path)
        os.rename(tmp_file, file_path)
        self._last_action_timing = current_milli_time() - start_time
        self.openDocument.emit(info)
        return file_path

    def edit(self, server_url, doc_id, user=None, download_url=None):
        try:
            log.debug("Editing doc %s on %s", doc_id, server_url)
            # Handle backward compatibility
            if '#' in doc_id:
                engine = self._get_engine(server_url)
                if engine is None:
                    log.warning(
                        'No engine found for %s, cannot edit file with remote ref %s',
                        server_url, doc_id)
                    return
                self._manager.edit(engine, doc_id)
            else:
                # Download file
                file_path = self._prepare_edit(server_url, doc_id, user=user, download_url=download_url)
                # Launch it
                if file_path is not None:
                    self._manager.open_local_file(file_path)
        except OSError as e:
            if e.errno == 13:
                # open file anyway
                if e.filename is not None:
                    self._manager.open_local_file(e.filename)
            else:
                raise e

    def _extract_edit_info(self, ref):
        dir_path = os.path.dirname(ref)
        uid = self._local_client.get_remote_id(dir_path)
        server_url = self._local_client.get_remote_id(dir_path, "nxdirectedit")
        user = self._local_client.get_remote_id(dir_path, "nxdirectedituser")
        engine = self._get_engine(server_url, user=user)
        if engine is None:
            raise NotFound()
        remote_client = engine.get_remote_doc_client()
        remote_client.check_suspended = self.stop_client
        digest_algorithm = self._local_client.get_remote_id(dir_path, "nxdirecteditdigestalgorithm")
        digest = self._local_client.get_remote_id(dir_path, "nxdirecteditdigest")
        return uid, engine, remote_client, digest_algorithm, digest

    def force_update(self, ref, digest):
        dir_path = os.path.dirname(ref)
        self._local_client.set_remote_id(dir_path, unicode(digest), "nxdirecteditdigest")
        self._upload_queue.put(ref)

    def _handle_queues(self):
        uploaded = False

        # Lock any documents
        while not self._lock_queue.empty():
            try:
                item = self._lock_queue.get_nowait()
            except Empty:
                break
            else:
                ref = item[0]
                log.trace('Handling DirectEdit lock queue ref: %r', ref)

            uid = ''
            dir_path = os.path.dirname(ref)
            try:
                uid, _, remote_client, _, _ = self._extract_edit_info(ref)
                if item[1] == 'lock':
                    remote_client.lock(uid)
                    self._local_client.set_remote_id(dir_path, '1', 'nxdirecteditlock')
                    # Emit the lock signal only when the lock is really set
                    self._manager.get_autolock_service().documentLocked.emit(os.path.basename(ref))
                else:
                    purge = False
                    try:
                        remote_client.unlock(uid)
                    except NotFound:
                        purge = True
                    if purge or item[1] == 'unlock_orphan':
                        path = self._local_client.abspath(ref)
                        log.trace('Remove orphan: %r', path)
                        self._manager.get_autolock_service().orphan_unlocked(path)
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        self._local_client.remove_remote_id(dir_path, 'nxdirecteditlock')
                        # Emit the signal only when the unlock is done
                        self._manager.get_autolock_service().documentUnlocked.emit(os.path.basename(ref))
            except ThreadInterrupt:
                raise
            except:
                # Try again in 30s
                log.exception('Cannot %s document %r', item[1], ref)
                self.directEditLockError.emit(item[1], os.path.basename(ref), uid)

        # Unqueue any errors
        item = self._error_queue.get()
        while item:
            self._upload_queue.put(item.get())
            item = self._error_queue.get()

        # Handle the upload queue
        while not self._upload_queue.empty():
            try:
                ref = self._upload_queue.get_nowait()
            except Empty:
                break
            else:
                log.trace('Handling DirectEdit queue ref: %r', ref)

            uid,  engine, remote_client, digest_algorithm, digest = self._extract_edit_info(ref)
            # Don't update if digest are the same
            info = self._local_client.get_info(ref)
            try:
                current_digest = info.get_digest(digest_func=digest_algorithm)
                if current_digest == digest:
                    continue

                start_time = current_milli_time()
                log.trace('Local digest: %s is different from the recorded one:'
                          ' %s - modification detected for %r',
                          current_digest, digest, ref)
                # TO_REVIEW Should check if server-side blob has changed ?
                # Update the document, should verify the remote hash NXDRIVE-187
                remote_info = remote_client.get_info(uid)
                if remote_info.digest != digest:
                    # Conflict detect
                    log.trace('Remote digest: %s is different from the recorded'
                              ' one: %s - conflict detected for %r',
                              remote_info.digest, digest, ref)
                    self.directEditConflict.emit(
                        os.path.basename(ref), ref, remote_info.digest)
                    continue

                os_path = self._local_client.abspath(ref)
                log.debug('Uploading file %r', os_path)
                remote_client.stream_update(
                    uid, os_path, apply_versioning_policy=True)
                # Update hash value
                dir_path = os.path.dirname(ref)
                self._local_client.set_remote_id(
                    dir_path, current_digest, 'nxdirecteditdigest')
                self._last_action_timing = current_milli_time() - start_time
                self.editDocument.emit(remote_info)
            except ThreadInterrupt:
                raise
            except:
                # Try again in 30s
                log.exception('DirectEdit unhandled error for ref %r', ref)
                self._error_queue.push(ref, ref)
                continue
            uploaded = True

        if uploaded:
            log.debug('Emitting directEditUploadCompleted')
            self.directEditUploadCompleted.emit()

        while not self.watchdog_queue.empty():
            evt = self.watchdog_queue.get()
            self.handle_watchdog_event(evt)

    def _execute(self):
        try:
            self.watchdog_queue = Queue()
            self._action = Action("Clean up folder")
            try:
                self._cleanup()
            except ThreadInterrupt:
                raise
            except Exception as ex:
                log.debug(ex)
            self._action = Action("Setup watchdog")
            self._setup_watchdog()
            self._end_action()
            # Load the target url if Drive was not launched before
            self.handle_url()
            if self._test:
                log.trace("DirectEdit Entering main loop: continue:%r pause:%r running:%r", self._continue, self._pause, self._running)
            while True:
                self._interact()
                if self._test:
                    log.trace("DirectEdit post interact: continue:%r pause:%r running:%r", self._continue, self._pause, self._running)
                try:
                    self._handle_queues()
                except NotFound:
                    pass
                except ThreadInterrupt:
                    raise
                except Exception as ex:
                    log.debug(ex)
                sleep(0.01)
        except ThreadInterrupt:
            raise
        finally:
            self._stop_watchdog()

    def get_metrics(self):
        metrics = super(DirectEdit, self).get_metrics()
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

    def _stop_watchdog(self):
        if self._observer is None:
            return
        log.info("Stopping FS Observer thread")
        try:
            self._observer.stop()
        except StandardError as e:
            log.warning('Cannot stop the FS observer: %r', e)
        # Wait for all observers to stop
        try:
            self._observer.join()
        except StandardError as e:
            log.warning('Cannot join the FS observer: %r', e)
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

            # Disable as we use the global open files instead of editor lock file
            if self.is_lock_file(file_name) and self._manager.get_direct_edit_auto_lock():
                if evt.event_type == 'created':
                    self._lock_queue.put((ref, 'lock'))
                elif evt.event_type == 'deleted':
                    self._lock_queue.put((ref, 'unlock'))
                return
            queue = False
            if evt.event_type in ('created', 'modified'):
                queue = True
            if evt.event_type == 'moved':
                ref = self._local_client.get_path(evt.dest_path)
                file_name = os.path.basename(evt.dest_path)
                src_path = evt.dest_path
                queue = True
            elif self._local_client.is_temp_file(file_name):
                return
            dir_path = self._local_client.get_path(os.path.dirname(src_path))
            name = self._local_client.get_remote_id(dir_path, "nxdirecteditname")
            if name is None:
                return
            if name != file_name:
                return
            if self._manager.get_direct_edit_auto_lock() and self._local_client.get_remote_id(dir_path, "nxdirecteditlock") != "1":
                self._manager.get_autolock_service().set_autolock(src_path, self)
            if queue:
                # ADD TO UPLOAD QUEUE
                self._upload_queue.put(ref)
                return
        except ThreadInterrupt:
            raise
        except StandardError:
            log.exception('Watchdog error')
        finally:
            self._end_action()
