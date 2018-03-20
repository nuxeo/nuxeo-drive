# coding: utf-8
import os
import shutil
import sys
from Queue import Empty, Queue
from logging import getLogger
from time import sleep
from urllib import quote

from PyQt4.QtCore import pyqtSignal, pyqtSlot
from watchdog.observers import Observer

from .client.base_automation_client import (DOWNLOAD_TMP_FILE_PREFIX,
                                            DOWNLOAD_TMP_FILE_SUFFIX)
from .client.common import BaseClient, NotFound
from .client.local_client import LocalClient
from .engine.activity import tooltip
from .engine.blacklist_queue import BlacklistQueue
from .engine.watcher.local_watcher import DriveFSEventHandler
from .engine.workers import ThreadInterrupt, Worker
from .utils import (current_milli_time, force_decode, guess_digest_algorithm,
                    normalize_event_filename, parse_protocol_url, simplify_url)

log = getLogger(__name__)


class DirectEdit(Worker):
    localScanFinished = pyqtSignal()
    directEditUploadCompleted = pyqtSignal(str)
    openDocument = pyqtSignal(object)
    editDocument = pyqtSignal(object)
    directEditLockError = pyqtSignal(str, str, str)
    directEditConflict = pyqtSignal(str, str, str)
    directEditError = pyqtSignal(str, dict)
    directEditReadonly = pyqtSignal(object)
    directEditLocked = pyqtSignal(object, object, object)

    def __init__(self, manager, folder, url):
        super(DirectEdit, self).__init__()

        self._manager = manager
        if isinstance(folder, bytes):
            folder = unicode(folder)
        self._folder = folder
        self.url = url

        self.autolock = self._manager.autolock_service
        self.use_autolock = self._manager.get_direct_edit_auto_lock()
        self._event_handler = None
        self._metrics = {'edit_files': 0}
        self._observer = None
        self._local_client = LocalClient(self._folder)
        self._upload_queue = Queue()
        self._lock_queue = Queue()
        self._error_queue = BlacklistQueue()
        self._stop = False
        self._last_action_timing = -1
        self.watchdog_queue = Queue()

        self._thread.started.connect(self.run)
        self.autolock.orphanLocks.connect(self._autolock_orphans)

    @pyqtSlot(object)
    def _autolock_orphans(self, locks):
        log.trace('Orphans lock: %r', locks)
        for lock in locks:
            if lock.path.startswith(self._folder):
                log.debug('Should unlock %r', lock.path)
                if not os.path.exists(lock.path):
                    self.autolock.orphan_unlocked(lock.path)
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
        url = url or self.url
        if not url:
            return

        log.debug('DirectEdit load: %r', url)

        try:
            info = parse_protocol_url(str(url))
        except UnicodeEncodeError:
            # Firefox seems to be different on the encoding part
            info = parse_protocol_url(unicode(url))

        if not info:
            return

        self.edit(info['server_url'],
                  info['doc_id'],
                  user=info['user'],
                  download_url=info['download_url'])

    @tooltip('Clean up folder')
    def _cleanup(self):
        """
        - Unlock any remaining doc that has not been unlocked
        - Upload forgotten changes
        - Remove obsolete folders
        """

        local = self._local_client

        if not local.exists('/'):
            os.mkdir(self._folder)
            return

        def purge(path):
            shutil.rmtree(local.abspath(path), ignore_errors=True)

        log.debug('Cleanup DirectEdit folder')

        for child in local.get_children_info('/'):
            children = local.get_children_info(child.path)
            if not children:
                purge(child.path)
                continue

            ref = children[0].path
            try:
                _,  _, _, func, digest = self._extract_edit_info(ref)
            except NotFound:
                # Engine is not known anymore
                purge(child.path)
                continue

            try:
                # Don't update if digest are the same
                info = local.get_info(ref)
                current_digest = info.get_digest(digest_func=func)
                if current_digest != digest:
                    log.warning('Document has been modified and '
                                'not synchronized, readd to upload queue')
                    self._upload_queue.put(ref)
                    continue
            except:
                log.exception('Unhandled clean-up error')
                continue

            # Place for handle reopened of interrupted Edit
            purge(child.path)

    def __get_engine(self, url, user=None):
        if not url:
            return None

        url = simplify_url(url)
        for engine in self._manager.get_engines().values():
            bind = engine.get_binder()
            server_url = bind.server_url.rstrip('/')
            if server_url == url and (user is None or user == bind.username):
                return engine

        # Some backend are case insensitive
        if not user:
            return None

        user = user.lower()
        for engine in self._manager.get_engines().values():
            bind = engine.get_binder()
            server_url = simplify_url(bind.server_url)
            if server_url == url and user == bind.username.lower():
                return engine

        return None

    def _get_engine(self, server_url, doc_id=None, user=None):
        engine = self.__get_engine(server_url, user=user)

        if not engine:
            values = {
                'user': force_decode(user) if user else 'Unknown',
                'server': server_url,
            }
            log.warning('No engine found for user %r on server %r, doc_id=%r',
                        user, server_url, doc_id)
            self.directEditError.emit('DIRECT_EDIT_CANT_FIND_ENGINE', values)
        elif engine.has_invalid_credentials():
            values = {'user': engine.remote_user, 'server': engine.server_url}
            log.warning('Invalid credentials for user %r on server %r',
                        engine.remote_user, engine.server_url)
            self.directEditError.emit('DIRECT_EDIT_INVALID_CREDS', values)
            engine = None

        return engine

    @staticmethod
    def _download(engine, remote_client, info, file_path, url=None):
        file_dir = os.path.dirname(file_path)
        file_name = os.path.basename(file_path)
        file_out = os.path.join(file_dir, DOWNLOAD_TMP_FILE_PREFIX + file_name
                                + DOWNLOAD_TMP_FILE_SUFFIX)

        # Close to processor method - should try to refactor ?
        pair = engine.get_dao().get_valid_duplicate_file(info.digest)
        if pair:
            local_client = engine.get_local_client()
            existing_file_path = local_client.abspath(pair.local_path)
            log.debug('Local file matches remote digest %r, copying it from %r',
                      info.digest, existing_file_path)
            shutil.copy(existing_file_path, file_out)
            if pair.is_readonly():
                log.debug('Unsetting readonly flag on copied file %r', file_out)
                BaseClient.unset_path_readonly(file_out)
        else:
            log.debug('Downloading file %r', info.filename)
            if url:
                remote_client.do_get(quote(url, safe='/:'),
                                     file_out=file_out,
                                     digest=info.digest,
                                     digest_algorithm=info.digest_algorithm)
            else:
                remote_client.get_blob(info, file_out=file_out)
        return file_out

    def _get_info(self, engine, remote, doc_id, user):
        doc = remote.fetch(
            doc_id,
            extra_headers={'fetch-document': 'lock'},
            enrichers=['permissions'],
        )
        info = remote.doc_to_info(doc, fetch_parent_uid=False)

        if info.lock_owner and info.lock_owner != engine.remote_user:
            log.debug('Doc %r was locked by %s on %s, edit not allowed',
                      info.name, info.lock_owner, info.lock_created)
            self.directEditLocked.emit(
                info.name, info.lock_owner, info.lock_created)
            info = None
        elif info.permissions and 'Write' not in info.permissions:
            log.debug('Doc %r is readonly for %s, edit not allowed',
                      info.name, user)
            self.directEditReadonly.emit(info.name)
            info = None

        return info

    def _prepare_edit(self, server_url, doc_id, user=None, download_url=None):
        start_time = current_milli_time()
        engine = self._get_engine(server_url, doc_id=doc_id, user=user)
        if not engine:
            return None

        # Get document info
        remote = engine.get_remote_doc_client()

        # Avoid any link with the engine, remote_doc are not cached so we
        # can do that
        remote.check_suspended = self.stop_client
        info = self._get_info(engine, remote, doc_id, user)
        if not info:
            return None

        filename = info.filename

        # Create local structure
        dir_path = os.path.join(self._folder, doc_id)
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)

        log.debug('Editing %r', filename)
        file_path = os.path.join(dir_path, filename)

        # Download the file
        url = None
        if download_url:
            url = server_url
            if not url.endswith('/'):
                url += '/'
            url += download_url

        tmp_file = self._download(engine, remote, info, file_path, url=url)
        if tmp_file is None:
            log.error('Download failed')
            return None

        # Set the remote_id
        local = self._local_client
        dir_path = local.get_path(os.path.dirname(file_path))
        local.set_remote_id(dir_path, doc_id)
        local.set_remote_id(dir_path, server_url, name='nxdirectedit')

        if user:
            local.set_remote_id(dir_path, user, name='nxdirectedituser')

        if info.digest:
            local.set_remote_id(dir_path, info.digest, name='nxdirecteditdigest')
            # Set digest algorithm if not sent by the server
            digest_algorithm = info.digest_algorithm
            if not digest_algorithm:
                digest_algorithm = guess_digest_algorithm(info.digest)
            local.set_remote_id(dir_path, digest_algorithm, name='nxdirecteditdigestalgorithm')
        local.set_remote_id(dir_path, filename, name='nxdirecteditname')

        # Rename to final filename
        # Under Windows first need to delete target file if exists,
        # otherwise will get a 183 WindowsError
        if sys.platform == 'win32' and os.path.exists(file_path):
            os.unlink(file_path)
        os.rename(tmp_file, file_path)

        self._last_action_timing = current_milli_time() - start_time
        self.openDocument.emit(info)
        return file_path

    def edit(self, server_url, doc_id, user=None, download_url=None):
        log.debug('Editing doc %s on %s', doc_id, server_url)
        try:
            # Download the file
            file_path = self._prepare_edit(
                server_url, doc_id, user=user, download_url=download_url)

            # Launch it
            if file_path:
                self._manager.open_local_file(file_path)
        except OSError as e:
            if e.errno == 13:
                # Open file anyway
                if e.filename is not None:
                    self._manager.open_local_file(e.filename)
            else:
                raise e

    def _extract_edit_info(self, ref):
        local = self._local_client
        dir_path = os.path.dirname(ref)
        server_url = local.get_remote_id(dir_path, name='nxdirectedit')
        user = local.get_remote_id(dir_path, name='nxdirectedituser')
        engine = self._get_engine(server_url, user=user)
        if not engine:
            raise NotFound()

        remote_client = engine.get_remote_doc_client()
        remote_client.check_suspended = self.stop_client
        digest_algorithm = local.get_remote_id(dir_path, name='nxdirecteditdigestalgorithm')
        digest = local.get_remote_id(dir_path, name='nxdirecteditdigest')
        uid = local.get_remote_id(dir_path)
        return uid, engine, remote_client, digest_algorithm, digest

    def force_update(self, ref, digest):
        local = self._local_client
        dir_path = os.path.dirname(ref)
        local.set_remote_id(dir_path, unicode(digest), name='nxdirecteditdigest')
        self._upload_queue.put(ref)

    def _handle_lock_queue(self):
        local = self._local_client

        while not self._lock_queue.empty():
            try:
                item = self._lock_queue.get_nowait()
            except Empty:
                break

            ref, action = item
            log.trace('Handling DirectEdit lock queue: action=%s, ref=%r',
                      action, ref)
            uid = ''
            dir_path = os.path.dirname(ref)

            try:
                uid, _, remote, _, _ = self._extract_edit_info(ref)
                if action == 'lock':
                    remote.lock(uid)
                    local.set_remote_id(dir_path, '1', name='nxdirecteditlock')
                    # Emit the lock signal only when the lock is really set
                    self.autolock.documentLocked.emit(os.path.basename(ref))
                    continue

                try:
                    remote.unlock(uid)
                except NotFound:
                    purge = True
                else:
                    purge = False

                if purge or action.startswith('unlock'):
                    path = local.abspath(ref)
                    log.trace('Remove orphan: %r', path)
                    self.autolock.orphan_unlocked(path)
                    shutil.rmtree(path, ignore_errors=True)
                    continue

                local.remove_remote_id(dir_path, name='nxdirecteditlock')
                # Emit the signal only when the unlock is done
                self.autolock.documentUnlocked.emit(os.path.basename(ref))
            except ThreadInterrupt:
                raise
            except:
                # Try again in 30s
                log.exception('Cannot %s document %r', action, ref)
                self.directEditLockError.emit(action, os.path.basename(ref), uid)

    def _handle_upload_queue(self):
        local = self._local_client

        while not self._upload_queue.empty():
            try:
                ref = self._upload_queue.get_nowait()
            except Empty:
                break

            log.trace('Handling DirectEdit queue ref: %r', ref)

            uid, engine, remote, digest_algorithm, digest = self._extract_edit_info(ref)
            # Don't update if digest are the same
            info = local.get_info(ref)
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
                remote_info = remote.get_info(uid)
                if remote_info.digest != digest:
                    # Conflict detect
                    log.trace('Remote digest: %s is different from the recorded'
                              ' one: %s - conflict detected for %r',
                              remote_info.digest, digest, ref)
                    self.directEditConflict.emit(
                        os.path.basename(ref), ref, remote_info.digest)
                    continue

                os_path = local.abspath(ref)
                log.debug('Uploading file %r', os_path)
                remote.stream_update(uid, os_path, apply_versioning_policy=True)

                # Update hash value
                dir_path = os.path.dirname(ref)
                local.set_remote_id(
                    dir_path, current_digest, name='nxdirecteditdigest')
                self._last_action_timing = current_milli_time() - start_time
                self.directEditUploadCompleted.emit(os.path.basename(os_path))
                self.editDocument.emit(remote_info)
            except ThreadInterrupt:
                raise
            except:
                # Try again in 30s
                log.exception('DirectEdit unhandled error for ref %r', ref)
                self._error_queue.push(ref, ref)

    def _handle_queues(self):
        # Lock any document
        self._handle_lock_queue()

        # Unqueue any errors
        for item in self._error_queue.get():
            self._upload_queue.put(item.get())

        # Handle the upload queue
        self._handle_upload_queue()

        while not self.watchdog_queue.empty():
            evt = self.watchdog_queue.get()
            self.handle_watchdog_event(evt)

    def _execute(self):
        try:
            self._cleanup()
            self._setup_watchdog()

            # Load the target URL if Drive was not launched before
            self.handle_url()

            while True:
                self._interact()
                try:
                    self._handle_queues()
                except NotFound:
                    pass
                except ThreadInterrupt:
                    raise
                except:
                    log.exception('Unhandled DirectEdit error')
                sleep(0.01)
        except ThreadInterrupt:
            raise
        finally:
            self._stop_watchdog()

    def get_metrics(self):
        metrics = super(DirectEdit, self).get_metrics()
        if self._event_handler:
            metrics['fs_events'] = self._event_handler.counter
        metrics['last_action_timing'] = self._last_action_timing
        metrics.update(self._metrics)
        return metrics

    @tooltip('Setup watchdog')
    def _setup_watchdog(self):
        log.debug('Watching FS modification on %r', self._folder)
        self._event_handler = DriveFSEventHandler(self)
        self._observer = Observer()
        self._observer.schedule(self._event_handler, self._folder, recursive=True)
        self._observer.start()

    def _stop_watchdog(self):
        if not self._observer:
            return

        log.info('Stopping FS Observer thread')
        try:
            self._observer.stop()
        except:
            log.exception('Cannot stop the FS observer')

        # Wait for the observer to stop
        try:
            self._observer.join()
        except:
            log.exception('Cannot join the FS observer')

        # Delete the observer
        self._observer = None

    @staticmethod
    def _is_lock_file(name):
        # type: (str) -> bool
        """
        Check if a given file name is a temporary one created by
        a tierce software.
        """

        return name.startswith((
            '~$',  # Microsoft Office
            '.~lock.',  # (Libre|Open)Office
        ))

    @tooltip('Handle watchdog event')
    def handle_watchdog_event(self, evt):
        try:
            src_path = normalize_event_filename(evt.src_path)

            # Event on the folder by itself
            if os.path.isdir(src_path):
                return

            local = self._local_client
            file_name = force_decode(os.path.basename(src_path))
            if local.is_temp_file(file_name):
                return

            log.debug('Handling watchdog event [%s] on %r',
                      evt.event_type, evt.src_path)

            if evt.event_type == 'moved':
                src_path = normalize_event_filename(evt.dest_path)
                file_name = force_decode(os.path.basename(src_path))

            ref = local.get_path(src_path)
            dir_path = local.get_path(os.path.dirname(src_path))
            name = local.get_remote_id(dir_path, name='nxdirecteditname')

            if not name:
                return

            editing = local.get_remote_id(dir_path, name='nxdirecteditlock')

            if force_decode(name) != file_name:
                if self._is_lock_file(file_name):
                    if (evt.event_type == 'created'
                            and self.use_autolock and editing != '1'):
                        """
                        [Windows 10] The original file is not modified until
                        we specifically click on the save button. Instead, it
                        applies changes to the temporary file.
                        So the auto-lock does not happen because there is no
                        'modified' event on the original file.
                        Here we try to address that by checking the lock state
                        and use the lock if not already done.
                        """
                        # Recompute the path from 'dir/temp_file' -> 'dir/file'
                        path = os.path.join(os.path.dirname(src_path), name)
                        self.autolock.set_autolock(path, self)
                    elif evt.event_type == 'deleted':
                        # Free the xattr to let _cleanup() does its work
                        local.remove_remote_id(dir_path, name='nxdirecteditlock')
                return

            if self.use_autolock and editing != '1':
                self.autolock.set_autolock(src_path, self)

            if evt.event_type != 'deleted':
                self._upload_queue.put(ref)
        except ThreadInterrupt:
            raise
        except:
            log.exception('Watchdog error')
