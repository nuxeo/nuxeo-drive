""" API to access local resources for synchronization. """

import errno
import os
import shutil
import unicodedata
import uuid
from contextlib import suppress
from datetime import datetime
from logging import getLogger
from pathlib import Path
from tempfile import mkdtemp
from time import mktime, strptime
from typing import Any, Callable, List, Optional, Tuple, Type, Union

from nuxeo.utils import get_digest_algorithm

from ...constants import LINUX, MAC, ROOT
from ...exceptions import DuplicationDisabledError, NotFound, UnknownDigest
from ...options import Options
from ...utils import (
    compute_digest,
    force_decode,
    lock_path,
    path_is_unc_name,
    safe_filename,
    safe_long_path,
    safe_rename,
    set_path_readonly,
    unlock_path,
    unset_path_readonly,
)

__all__ = ("FileInfo", "get")

log = getLogger(__name__)


class FileInfo:
    """Data Transfer Object for file info on the Local FS."""

    def __init__(
        self,
        root: Path,
        path: Path,
        folderish: bool,
        last_modification_time: datetime,
        /,
        *,
        digest_func: str = "md5",
        digest_callback: Callable = None,
        remote_ref: str = "",
        size: int = 0,
    ) -> None:
        # Function to check during long-running processing like digest
        # computation if the synchronization thread needs to be suspended
        self.digest_callback = digest_callback

        filepath = root / path
        self.path = Path(unicodedata.normalize("NFC", str(path)))
        self.filepath = Path(unicodedata.normalize("NFC", str(filepath)))

        # NXDRIVE-188: normalize name on the file system if not normalized
        if not MAC and filepath.exists() and self.filepath != filepath:
            log.info(f"Forcing normalization of {filepath!r} to {self.filepath!r}")
            safe_rename(filepath, self.filepath)

        if folderish:
            size = 0
        else:
            # Guess the file size to help catching file changes in the watcher.
            # This will prevent to do checksum comparisons, which are expensive.
            if size == 0:
                with suppress(FileNotFoundError):
                    size = self.filepath.stat().st_size
        self.size = size

        self.folderish = folderish  # True if a Folder
        self.remote_ref = remote_ref

        # Last OS modification date of the file
        self.last_modification_time = last_modification_time

        # Function to use
        self._digest_func = digest_func

        # Precompute base name once and for all as it's often useful in practice
        self.name = self.filepath.name

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}<path={self.path!r}, filepath={self.filepath!r},"
            f" name={self.name!r}, folderish={self.folderish!r},"
            f" size={self.size}, remote_ref={self.remote_ref!r}>"
        )

    def get_digest(self, *, digest_func: str = None) -> str:
        """Lazy computation of the digest."""
        digest_func = str(digest_func or self._digest_func)
        return compute_digest(self.filepath, digest_func, callback=self.digest_callback)


class LocalClientMixin:
    """The base class for client API implementation for the local file system."""

    def __init__(
        self,
        base_folder: Path,
        /,
        *,
        digest_callback: Callable = None,
        download_dir: Path = ROOT,
    ) -> None:
        self._digest_func = "md5"

        # Function to check during long-running processing like digest
        # computation if the synchronization thread needs to be suspended
        self.digest_callback = digest_callback

        self.base_folder = base_folder.resolve()

        # The download folder from the engine, mostly used in .rename()
        self.download_dir = download_dir

        self._case_sensitive: Optional[bool] = None
        self._local_folder_is_unc_name = path_is_unc_name(self.base_folder)

    def __repr__(self) -> str:
        return (
            f"<{type(self).__name__}"
            f" base_folder={self.base_folder!r},"
            f" is_case_sensitive={self._case_sensitive!r}"
            ">"
        )

    def can_use_trash(self) -> bool:
        """Allow to use the local trash mechanisms."""
        # On GNU/Linux and macOS, we do want to use the trash.
        # On Windows, it is only possible with non-UNC names (\\Server\shared-folder).
        return not self._local_folder_is_unc_name

    def is_case_sensitive(self) -> bool:
        if self._case_sensitive is None:
            try:
                path = mkdtemp(prefix=".caseTest_")
                self._case_sensitive = not os.path.isdir(path.upper())
                os.rmdir(path)
            except OSError:
                # For instance, %TEMP% may be restricted on Windows.
                # Assume False but log the error to help improve that code.
                log.error("Cannot check for case sensitivity", exc_info=True)
                self._case_sensitive = False
        return self._case_sensitive

    @staticmethod
    def is_temp_file(filepath: Path, /) -> bool:
        return Options.nxdrive_home / "tmp" in filepath.parents

    def set_readonly(self, ref: Path, /) -> None:
        path = self.abspath(ref)
        set_path_readonly(path)

    def unset_readonly(self, ref: Path, /) -> None:
        path = self.abspath(ref)
        if path.exists():
            unset_path_readonly(path)

    def clean_xattr_root(self) -> None:
        with suppress(Exception):
            self.remove_root_id(cleanup=True)
        self.clean_xattr_folder_recursive(ROOT, cleanup=True)

    def clean_xattr_folder_recursive(
        self, path: Path, /, *, cleanup: bool = False
    ) -> None:
        for child in self.get_children_info(path):
            try:
                self.remove_remote_id(child.path, cleanup=cleanup)
            except Exception:
                log.warning(f"Cannot clean {child.filepath!r}", exc_info=True)
            if child.folderish:
                self.clean_xattr_folder_recursive(child.path)

    def remove_root_id(self, *, cleanup: bool = False) -> None:
        self.remove_remote_id(ROOT, name="ndriveroot", cleanup=cleanup)

    def set_root_id(self, value: bytes, /) -> None:
        self.set_remote_id(ROOT, value, name="ndriveroot")

    def get_root_id(self) -> str:
        return self.get_remote_id(ROOT, name="ndriveroot")

    def remove_remote_id_impl(self, ref: Path, /, *, name: str = "ndrive") -> None:
        """Remove a given extended attribute. Need to be implemented by subclasses."""
        raise NotImplementedError()

    def remove_remote_id(
        self, ref: Path, /, *, name: str = "ndrive", cleanup: bool = False
    ) -> None:
        path = self.abspath(ref)
        log.debug(f"Removing xattr {name!r} from {path!r}")
        locker = unlock_path(path, unlock_parent=False)
        try:
            self.remove_remote_id_impl(path, name=name)
        except OSError as exc:
            # ENOENT: file does not exist
            # OSError [Errno 93]: Attribute not found
            if exc.errno not in (errno.ENOENT, 93):
                raise exc
        finally:
            # Relock the path by default. It is not needed when using the clean-folder CLI arg.
            if not cleanup:
                lock_path(path, locker)

    def has_folder_icon(self, ref: Path, /) -> bool:
        """Check if the folder icon is set. Need to be implemented by subclasses."""
        raise NotImplementedError()

    def set_folder_icon(self, ref: Path, icon: Path, /) -> None:
        """Create a special file to customize the folder icon.
        Need to be implemented by subclasses.
        """
        raise NotImplementedError()

    def set_remote_id(
        self, ref: Path, remote_id: Union[bytes, str], /, *, name: str = "ndrive"
    ) -> None:
        path = self.abspath(ref)
        log.debug(f"Setting xattr {name!r} with value {remote_id!r} on {path!r}")
        self.set_path_remote_id(path, remote_id, name=name)

    @staticmethod
    def set_path_remote_id(
        path: Path, remote_id: Union[bytes, str], /, *, name: str = "ndrive"
    ) -> None:
        raise NotImplementedError()

    def get_remote_id(self, ref: Path, /, *, name: str = "ndrive") -> str:
        path = self.abspath(ref)
        value = self.get_path_remote_id(path, name=name)
        log.debug(f"Getting xattr {name!r} from {path!r}: {value!r}")
        return value

    @staticmethod
    def get_path_remote_id(path: Path, /, *, name: str = "ndrive") -> str:
        """Get a given extended attribute from a file/folder. Need to be implemented by subclasses."""
        raise NotImplementedError()

    def get_info(self, ref: Path, /, *, check: bool = True) -> FileInfo:
        if check:
            # All use cases except Direct Transfer
            os_path = self.abspath(ref)
            if not os_path.exists():
                raise NotFound(
                    f"Could not find doc into {self.base_folder!r}: "
                    f"ref={ref!r}, os_path={os_path!r}"
                )
        else:
            # Direct Transfer, *ref* is an absolute local path
            os_path = ref

        folderish = os_path.is_dir()
        stat_info = os_path.stat()
        size = 0 if folderish else stat_info.st_size
        try:
            mtime = datetime.utcfromtimestamp(stat_info.st_mtime)
        except (ValueError, OverflowError, OSError) as e:
            log.warning(
                f"{e} file path: {os_path}. st_mtime value: {stat_info.st_mtime}"
            )
            mtime = datetime.utcfromtimestamp(0)

        # TODO Do we need to load it every time ?
        remote_ref = self.get_remote_id(ref)
        # On unix we could use the inode for file move detection but that won't
        # work on Windows. To reduce complexity of the code and the possibility
        # to have Windows specific bugs, let's not use the unix inode at all.
        # uid = str(stat_info.st_ino)
        return FileInfo(
            self.base_folder,
            ref,
            folderish,
            mtime,
            digest_func=self._digest_func,
            digest_callback=self.digest_callback,
            remote_ref=remote_ref,
            size=size,
        )

    def try_get_info(self, ref: Path, /) -> Optional[FileInfo]:
        try:
            return self.get_info(ref)
        except NotFound:
            return None

    def is_equal_digests(
        self,
        local_digest: Optional[str],
        remote_digest: Optional[str],
        local_path: Path,
        /,
        *,
        remote_digest_algorithm: str = None,
    ) -> bool:
        """
        Compare 2 document's digests.

        :param str local_digest: Digest of the local document.
                                 Set to None to force digest computation.
        :param str remote_digest: Digest of the remote document.
        :param str local_path: Local path of the document.
        :param str remote_digest_algorithm: Remote document digest algorithm
        :return bool: Digest are equals.
        """

        if local_digest == remote_digest:
            return True

        if remote_digest_algorithm is None:
            if not remote_digest:
                return False
            remote_digest_algorithm = get_digest_algorithm(remote_digest)
            if not remote_digest_algorithm:
                raise UnknownDigest(str(remote_digest))

        file_info = self.try_get_info(local_path)
        if not file_info:
            return False
        digest = file_info.get_digest(digest_func=remote_digest_algorithm)
        return digest == remote_digest

    def is_ignored(self, parent_ref: Path, file_name: str, /) -> bool:
        """Note: added parent_ref to be able to filter on size if needed."""

        file_name = safe_filename(force_decode(file_name.lower()))

        if file_name.endswith(Options.ignored_suffixes) or file_name.startswith(
            Options.ignored_prefixes
        ):
            return True

        # NXDRIVE-655: need to check every parent if they are ignored
        result = False
        if parent_ref != ROOT:
            file_name = parent_ref.name
            parent_ref = parent_ref.parent
            result = self.is_ignored(parent_ref, file_name)

        return result

    def _get_children_info(self, ref: Path, /) -> List[FileInfo]:
        os_path = self.abspath(ref)
        result = []

        for child in sorted(os_path.iterdir()):
            if self.is_ignored(ref, child.name) or self.is_temp_file(child):
                log.info(f"Ignoring banned file {child.name!r} in {os_path!r}")
                continue

            child_ref = ref / child.name
            try:
                info = self.get_info(child_ref)
            except NotFound:
                log.warning(
                    "The child file has been deleted in the mean time"
                    " or while reading some of its attributes"
                )
                continue
            if info:
                result.append(info)

        return result

    def get_children_info(self, ref: Path, /) -> List[FileInfo]:
        try:
            return self._get_children_info(ref)
        except FileNotFoundError as exc:
            log.warning(str(exc))
            return []

    def unlock_ref(
        self, ref: Path, /, *, unlock_parent: bool = True, is_abs: bool = False
    ) -> int:
        path = ref if is_abs else self.abspath(ref)
        return unlock_path(path, unlock_parent=unlock_parent)

    def lock_ref(self, ref: Path, locker: int, /, *, is_abs: bool = False) -> None:
        path = ref if is_abs else self.abspath(ref)
        lock_path(path, locker)

    def make_folder(self, parent: Path, name: str, /) -> Path:
        os_path, name = self._abspath_deduped(parent, name)
        locker = self.unlock_ref(parent, unlock_parent=False)
        try:
            os_path.mkdir(parents=True, exist_ok=True)
        finally:
            self.lock_ref(parent, locker)

        # Name should be the actual name of the folder created locally
        return parent / os_path.name

    def get_new_file(self, parent: Path, name: str, /) -> Tuple[Path, Path, str]:
        os_path, name = self._abspath_deduped(parent, name)
        return parent / name, os_path, name

    def delete(self, ref: Path, /) -> None:
        os_path = self.abspath(ref)
        if not os_path.exists():
            return

        log.debug(f"Trashing {os_path!r}")
        locker = self.unlock_ref(os_path, is_abs=True)
        try:
            self.trash(os_path)
        except OSError:
            log.warning(
                f"Trash not possible, deleting permanently {os_path!r}", exc_info=True
            )
            try:
                self.delete_final(ref)
            except OSError as exc:
                log.warning(f"Cannot delete {os_path!r}")
                with suppress(Exception):
                    # WindowsError(None, None, path, retcode)
                    _, _, _, retcode = exc.args
                    setattr(exc, "winerror", retcode)
                setattr(exc, "trash_issue", True)
                raise exc
        finally:
            # Don't want to unlock the current deleted
            self.lock_ref(os_path, locker & 2, is_abs=True)

    def delete_final(self, ref: Path, /) -> None:
        """Completely remove a given file or folder. Untrash is not possible then."""
        error = None

        def onerror(func: Any, path: Path, exc_info: Any) -> None:
            """Assign the error only once."""
            nonlocal error
            if not error:
                error = exc_info[1]

        log.debug(f"Permanently deleting {ref!r}")
        locker = 0
        parent_ref = None
        try:
            if ref != ROOT:
                parent_ref = ref.parent
                locker = self.unlock_ref(parent_ref, unlock_parent=False)
            self.unset_readonly(ref)
            os_path = self.abspath(ref)
            if os_path.is_dir():
                # Override `onerror` to catch the 1st exception and let other
                # documents to be deleted.
                shutil.rmtree(os_path, onerror=onerror)
                if error:
                    raise error
            else:
                os_path.unlink(missing_ok=True)
        finally:
            if parent_ref is not None:
                self.lock_ref(parent_ref, locker)

    def exists(self, ref: Path, /) -> bool:
        try:
            return self.abspath(ref).exists()
        except OSError:
            pass
        except Exception:
            log.exception("Unhandled error")
        return False

    def set_file_attribute(self, path: Path) -> None:
        """Set a special attribute (not extended attribute) to a given file.
        Here we do not raise NotImplementedError because this is only used on Windows.
        So instead of declaring an no-op method in the GNU/Linux and macOS class, we
        just do nothing here by default.
        """
        pass

    def rename(self, ref: Path, to_name: str, /) -> FileInfo:
        """Rename a local file or folder."""
        new_name = safe_filename(to_name)
        source_os_path = self.abspath(ref)
        parent = ref.parent
        old_name = ref.name
        locker = self.unlock_ref(source_os_path, is_abs=True)
        try:
            # Check if only case renaming
            if (
                old_name != new_name
                and old_name.lower() == new_name.lower()
                and not self.is_case_sensitive()
            ):
                # The filesystem is not sensitive, so we cannot rename
                # from "a" to "A". We need to use a temporary filename
                # in between, which allows us to do "a" -> <tempname> -> "A".
                temp_path = self.download_dir / str(uuid.uuid4())
                source_os_path.rename(temp_path)
                source_os_path = temp_path
                # Try the os rename part
                target_os_path = self.abspath(parent / new_name)
            else:
                target_os_path, new_name = self._abspath_deduped(
                    parent, new_name, old_name=old_name
                )
            if old_name != new_name:
                safe_rename(source_os_path, target_os_path)
            self.set_file_attribute(target_os_path)
            new_ref = parent / new_name
            return self.get_info(new_ref)
        finally:
            self.lock_ref(source_os_path, locker & 2, is_abs=True)

    def move(self, ref: Path, new_parent_ref: Path, /, *, name: str = None) -> FileInfo:
        """Move a local file or folder into another folder."""

        if ref == ROOT:
            raise ValueError("Cannot move the toplevel folder.")

        name = name or ref.name
        filename = self.abspath(ref)
        target_os_path, new_name = self._abspath_deduped(new_parent_ref, name)
        locker = self.unlock_ref(filename, is_abs=True)
        parent = target_os_path.parent
        new_locker = self.unlock_ref(parent, unlock_parent=False, is_abs=True)
        try:
            safe_rename(filename, target_os_path)
            new_ref = new_parent_ref / new_name
            return self.get_info(new_ref)
        finally:
            self.lock_ref(filename, locker & 2, is_abs=True)
            self.lock_ref(parent, locker & 1 | new_locker, is_abs=True)

    def change_created_time(self, filepath: Path, d_ctime: datetime, /) -> None:
        """Change the created time of a given file.
        Here we do not raise NotImplementedError because there is no concept of
        creation time on GNU/Linux. So instead of declaring an no-op method in
        the GNU/Linux class, we just do nothing here by default.
        """
        pass

    def change_file_date(
        self, filepath: Path, /, *, mtime: str = None, ctime: str = None
    ) -> None:
        """
        Change the FS modification and creation dates of a file.

        Since there is no creation time on GNU/Linux, the ctime
        will not be taken into account if running on this platform.

        :param filename: The file to modify
        :param mtime: The modification time
        :param ctime: The creation time
        """
        filepath = safe_long_path(filepath)

        log.debug(
            f"Setting file dates for {filepath!r} (ctime={ctime!r}, mtime={mtime!r})"
        )

        # Set the creation time first as on macOS using touch will change ctime and mtime.
        # The modification time will be updated just after, if needed.
        if ctime:
            d_ctime = datetime.strptime(str(ctime), "%Y-%m-%d %H:%M:%S")
            self.change_created_time(filepath, d_ctime)

        if mtime:
            d_mtime = mktime(strptime(str(mtime), "%Y-%m-%d %H:%M:%S"))
            os.utime(filepath, (d_mtime, d_mtime))

    def get_path(self, target: Path, /) -> Path:
        """Relative path to the local client from an absolute OS path."""
        # NXDRIVE-2485: using os.path.realpath() instead of Path.resolve() and Path.absolute().
        try:
            return Path(os.path.realpath(target)).relative_to(self.base_folder)
        except ValueError:
            # From the Path.relative_to() doc: if the operation is not possible
            # (because this is not a subpath of the other path), raise ValueError.
            return ROOT

    def abspath(self, ref: Path, /) -> Path:
        """Absolute path on the operating system."""
        return safe_long_path(self.base_folder / ref)

    def _abspath_deduped(
        self, parent: Path, orig_name: str, /, *, old_name: str = None
    ) -> Tuple[Path, str]:
        """Absolute path on the operating system with deduplicated names."""

        # Make name safe by removing invalid chars
        name = safe_filename(orig_name)

        os_path = self.abspath(parent / name)
        if old_name == name or not os_path.exists():
            return os_path, name

        raise DuplicationDisabledError("De-duplication is disabled")

    def trash(self, path: Path, /) -> None:
        """Move a given file or folder to the trash. Untrash is possible then."""
        raise NotImplementedError()


def get() -> Type[LocalClientMixin]:
    """Factory to get the appropriate local client class depending of the OS."""
    if LINUX:
        from . import linux

        return linux.LocalClient

    if MAC:
        from . import darwin

        return darwin.LocalClient

    from . import windows

    return windows.LocalClient
