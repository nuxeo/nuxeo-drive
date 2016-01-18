__author__ = 'loopingz'
from nxdrive.engine.processor import Processor as OldProcessor
from nxdrive.logging_config import get_logger
from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_PREFIX
from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_SUFFIX
log = get_logger(__name__)
import os


class Processor(OldProcessor):
    def __init__(self, engine, item_getter, name=None):
        super(Processor, self).__init__(engine, item_getter, name)

    def acquire_state(self, row_id):
        log.warn("acquire...")
        result = super(Processor, self).acquire_state(row_id)
        if result is not None and self._engine.get_local_watcher().is_pending_scan(result.local_parent_path):
            self._dao.release_processor(self._thread_id)
            # Postpone pair for watcher delay
            self._engine.get_queue_manager().postpone_pair(result, self._engine.get_local_watcher().get_scan_delay())
            return None
        log.warn("Acquired: %r", result)
        return result

    def _get_partial_folders(self):
        path = self._engine.get_local_client()._abspath('/.partials')
        if not os.path.exists(path):
            os.mkdir(path)
        return path

    def _download_content(self, local_client, remote_client, doc_pair, file_path):

        # Should share between threads
        file_out = os.path.join(self._get_partial_folders(), DOWNLOAD_TMP_FILE_PREFIX +
                            doc_pair.remote_digest + DOWNLOAD_TMP_FILE_SUFFIX)
        # Check if the file is already on the HD
        pair = self._dao.get_valid_duplicate_file(doc_pair.remote_digest)
        if pair:
            import shutil
            shutil.copy(local_client._abspath(pair.local_path), file_out)
            return file_out
        tmp_file = remote_client.stream_content( doc_pair.remote_ref, file_path,
                                parent_fs_item_id=doc_pair.remote_parent_ref, file_out=file_out)
        self._update_speed_metrics()
        return tmp_file

    def _update_remotely(self, doc_pair, local_client, remote_client, is_renaming):
        log.warn("_update_remotely")
        os_path = local_client._abspath(doc_pair.local_path)
        if is_renaming:
            new_os_path = os.path.join(os.path.dirname(os_path), doc_pair.remote_name)
            log.debug("Replacing local file '%s' by '%s'.", os_path, new_os_path)
        else:
            new_os_path = os_path
        log.debug("Updating content of local file '%s'.", os_path)
        tmp_file = self._download_content(local_client, remote_client, doc_pair, new_os_path)
        # Delete original file and rename tmp file
        remote_id = local_client.get_remote_id(doc_pair.local_path)
        local_client.delete_final(doc_pair.local_path)
        # Move rename
        updated_info = local_client.move(local_client.get_path(tmp_file),
                                        doc_pair.local_parent_path, doc_pair.remote_name)
        if remote_id is not None:
            local_client.set_remote_id(doc_pair.local_parent_path + '/' + doc_pair.remote_name, doc_pair.remote_ref)
        doc_pair.local_digest = updated_info.get_digest()
        self._dao.update_last_transfer(doc_pair.id, "download")
        self._refresh_local_state(doc_pair, updated_info)

    def _create_remotely(self, local_client, remote_client, doc_pair, parent_pair, name):
        local_parent_path = parent_pair.local_path
        # TODO Shared this locking system / Can have concurrent lock
        self._unlock_readonly(local_client, local_parent_path)
        tmp_file = None
        try:
            if doc_pair.folderish:
                log.debug("Creating local folder '%s' in '%s'", name,
                          local_client._abspath(parent_pair.local_path))
                # Might want do temp name to original
                path = local_client.make_folder(local_parent_path, name)

            else:
                path, os_path, name = local_client.get_new_file(local_parent_path,
                                                                name)
                tmp_file = self._download_content(local_client, remote_client, doc_pair, os_path)
                log.debug("Creating local file '%s' in '%s'", name,
                          local_client._abspath(parent_pair.local_path))
                # Move file to its folder - might want to split it in two for events
                local_client.move(local_client.get_path(tmp_file),local_parent_path, name)
                self._dao.update_last_transfer(doc_pair.id, "download")
        finally:
            self._lock_readonly(local_client, local_parent_path)
            # Clean .nxpart if needed
            if tmp_file is not None and os.path.exists(tmp_file):
                os.remove(tmp_file)
        return path

    def _scan_recursive(self, info, recursive=True):
        log.debug('Starting recursive local scan of %r', info.path)
        if recursive:
            # Don't interact if only one level
            self._interact()

        # Load all children from DB
        log.trace('Starting to get DB local children for %r', info.path)
        db_children = self._dao.get_local_children(info.path)

        # Create a list of all children by their name
        children = dict()
        to_scan = []
        to_scan_new = []
        for child in db_children:
            children[child.local_name] = child

        # Load all children from FS
        # detect recently deleted children
        log.trace('Starting to get FS children info for %r', info.path)
        try:
            fs_children_info = self.client.get_children_info(info.path)
        except OSError:
            # The folder has been deleted in the mean time
            return

        # Get remote children to be able to check if a local child found during the scan is really a new item
        # or if it is just the result of a remote creation performed on the file system but not yet updated in the DB
        # as for its local information
        remote_children = []
        parent_remote_id = self.client.get_remote_id(info.path)
        if parent_remote_id is not None:
            remote_children_pairs = self._dao.get_new_remote_children(parent_remote_id)
            for remote_child_pair in remote_children_pairs:
                remote_children.append(remote_child_pair.remote_name)

        # recursively update children
        for child_info in fs_children_info:
            child_name = os.path.basename(child_info.path)
            child_type = 'folder' if child_info.folderish else 'file'
            if child_name not in children:
                try:
                    remote_id = self.client.get_remote_id(child_info.path)
                    if remote_id is None:
                        # Avoid IntegrityError: do not insert a new pair state if item is already referenced in the DB
                        if remote_children and child_name in remote_children:
                            log.debug('Skip potential new %s as it is the result of a remote creation: %r',
                                      child_type, child_info.path)
                            continue
                        log.debug("Found new %s %s", child_type, child_info.path)
                        self._metrics['new_files'] = self._metrics['new_files'] + 1
                        self._dao.insert_local_state(child_info, info.path)
                    else:
                        log.debug("Found potential moved file %s[%s]", child_info.path, remote_id)
                        doc_pair = self._dao.get_normal_state_from_remote(remote_id)
                        if doc_pair is not None and self.client.exists(doc_pair.local_path):
                            # possible move-then-copy case, NXDRIVE-471
                            child_full_path = self.client._abspath(child_info.path)
                            child_creation_time = self.get_creation_time(child_full_path)
                            doc_full_path = self.client._abspath(doc_pair.local_path)
                            doc_creation_time = self.get_creation_time(doc_full_path)
                            log.trace('child_cre_time=%f, doc_cre_time=%f', child_creation_time, doc_creation_time)
                        if doc_pair is None:
                            log.debug("Can't find reference for %s in database, put it in locally_created state",
                                      child_info.path)
                            self._metrics['new_files'] = self._metrics['new_files'] + 1
                            # Should remove remote id
                            self._dao.insert_local_state(child_info, info.path)
                            self._protected_files[remote_id] = True
                        elif doc_pair.processor > 0:
                            log.debug('Skip pair as it is being processed: %r', doc_pair)
                            continue
                        elif doc_pair.local_path == child_info.path:
                            # Should not happen
                            log.debug('Skip pair as it is not a real move: %r', doc_pair)
                            continue
                        elif not self.client.exists(doc_pair.local_path) or \
                                ( self.client.exists(doc_pair.local_path) and child_creation_time < doc_creation_time):
                                # If file exists at old location, and the file at the original location is newer,
                                #   it is moved to the new location earlier then copied back
                            log.debug("Found moved file")
                            doc_pair.local_state = 'moved'
                            self._dao.update_local_state(doc_pair, child_info)
                            self._protected_files[doc_pair.remote_ref] = True
                            if self.client.exists(doc_pair.local_path) and child_creation_time < doc_creation_time:
                                # Need to put back the new created - need to check maybe if already there
                                log.trace("Found a moved file that has been copy/paste back: %s", doc_pair.local_path)
                                self.client.remove_remote_id(doc_pair.local_path)
                                self._dao.insert_local_state(self.client.get_info(doc_pair.local_path), os.path.dirname(doc_pair.local_path))
                        else:
                            # File still exists - must check the remote_id
                            old_remote_id = self.client.get_remote_id(doc_pair.local_path)
                            if old_remote_id == remote_id:
                                # Local copy paste
                                log.debug("Found a copy-paste of document")
                                self.client.remove_remote_id(child_info.path)
                                self._dao.insert_local_state(child_info, info.path)
                            else:
                                # Moved and renamed
                                log.debug("Moved and renamed: %r", doc_pair)
                                old_pair = self._dao.get_normal_state_from_remote(old_remote_id)
                                if old_pair is not None:
                                    old_pair.local_state = 'moved'
                                    # Check digest also
                                    digest = child_info.get_digest()
                                    if old_pair.local_digest != digest:
                                        old_pair.local_digest = digest
                                    self._dao.update_local_state(old_pair, self.client.get_info(doc_pair.local_path))
                                    self._protected_files[old_pair.remote_ref] = True
                                doc_pair.local_state = 'moved'
                                # Check digest also
                                digest = child_info.get_digest()
                                if doc_pair.local_digest != digest:
                                    doc_pair.local_digest = digest
                                self._dao.update_local_state(doc_pair, child_info)
                                self._protected_files[doc_pair.remote_ref] = True
                    if child_info.folderish:
                        to_scan_new.append(child_info)
                except Exception as e:
                    log.error('Error during recursive scan of %r, ignoring until next full scan', child_info.path,
                              exc_info=True)
                    continue
            else:
                child_pair = children.pop(child_name)
                try:
                    if (unicode(child_info.last_modification_time.strftime("%Y-%m-%d %H:%M:%S"))
                            != child_pair.last_local_updated.split(".")[0] and child_pair.processor == 0):
                        log.trace("Update file %s", child_info.path)
                        remote_ref = self.client.get_remote_id(child_pair.local_path)
                        if remote_ref is not None and child_pair.remote_ref is None:
                            log.debug("Possible race condition between remote and local scan, let's refresh pair: %r",
                                      child_pair)
                            child_pair = self._dao.get_state_from_id(child_pair.id)
                            if child_pair.remote_ref is None:
                                log.debug("Pair not yet handled by remote scan (remote_ref is None) but existing"
                                          " remote_id xattr, let's set it to None: %r", child_pair)
                                self.client.remove_remote_id(child_pair.local_path)
                                remote_ref = None
                        if remote_ref != child_pair.remote_ref:
                            # TO_REVIEW
                            # Load correct doc_pair | Put the others one back to children
                            log.warn("Detected file substitution: %s (%s/%s)", child_pair.local_path, remote_ref,
                                     child_pair.remote_ref)
                            if remote_ref is None and not child_info.folderish:
                                # Alternative stream or xattr can have been removed by external software or user
                                digest = child_info.get_digest()
                                if child_pair.local_digest != digest:
                                    child_pair.local_digest = digest
                                    child_pair.local_state = 'modified'
                                self.client.set_remote_id(child_pair.local_path, child_pair.remote_ref)
                                self._dao.update_local_state(child_pair, child_info)
                                continue
                            old_pair = self._dao.get_normal_state_from_remote(remote_ref)
                            if old_pair is None:
                                self._dao.insert_local_state(child_info, info.path)
                            else:
                                old_pair.local_state = 'moved'
                                # Check digest also
                                digest = child_info.get_digest()
                                if old_pair.local_digest != digest:
                                    old_pair.local_digest = digest
                                self._dao.update_local_state(old_pair, child_info)
                                self._protected_files[old_pair.remote_ref] = True
                            self._delete_files[child_pair.remote_ref] = child_pair
                        if not child_info.folderish:
                            digest = child_info.get_digest()
                            if child_pair.local_digest != digest:
                                child_pair.local_digest = digest
                                child_pair.local_state = 'modified'
                        self._metrics['update_files'] = self._metrics['update_files'] + 1
                        self._dao.update_local_state(child_pair, child_info)
                    if child_info.folderish:
                        to_scan.append(child_info)
                except Exception as e:
                    log.exception(e)
                    self.increase_error(child_pair, "SCAN RECURSIVE", exception=e)
                    continue

        for deleted in children.values():
            if deleted.pair_state == "remotely_created":
                continue
            log.debug("Found deleted file %s", deleted.local_path)
            # May need to count the children to be ok
            self._metrics['delete_files'] = self._metrics['delete_files'] + 1
            if deleted.remote_ref is None:
                self._dao.remove_state(deleted)
            else:
                self._delete_files[deleted.remote_ref] = deleted

        for child_info in to_scan_new:
            self._push_to_scan(child_info)

        if not recursive:
            log.debug('Ended recursive local scan of %r', info.path)
            return

        for child_info in to_scan:
            self._push_to_scan(child_info)

        log.debug('Ended recursive local scan of %r', info.path)
