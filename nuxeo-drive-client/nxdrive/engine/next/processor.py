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
        local_client = self._engine.get_local_client()
        if not local_client.exists('/.partials'):
            local_client.make_folder('/', '.partials')
        return local_client._abspath('/.partials')

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
        rel_path = local_client.get_path(tmp_file)
        local_client.set_remote_id(rel_path, doc_pair.remote_ref)
        # Move rename
        updated_info = local_client.move(rel_path,
                                        doc_pair.local_parent_path, doc_pair.remote_name)
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
