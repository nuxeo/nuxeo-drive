from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .engine.engine import Engine  # noqa


class DriveError(Exception):
    """Mother exception."""

    pass


class AddonForbiddenError(DriveError):
    """The nuxeo-drive addon access is not allowed to the current user."""

    pass


class AddonNotInstalledError(DriveError):
    """The nuxeo-drive addon is not installed on the server."""

    pass


class DocumentAlreadyLocked(DriveError):
    """In Direct Edit, a document is locked by someone else."""

    def __init__(self, username: str, /) -> None:
        self.username = username

    def __repr__(self) -> str:
        return f"Document already locked by {self.username!r}"

    def __str__(self) -> str:
        return repr(self)


class DuplicationDisabledError(ValueError):
    """
    Exception raised when de-duplication is disabled and there is a
    file collision.
    """

    pass


class EngineInitError(DriveError):
    """Impossible to initialize a Engine."""

    def __init__(self, engine: "Engine", /) -> None:
        self.engine = engine

    def __repr__(self) -> str:
        return f"Engine initialization error for {self.engine!r}"

    def __str__(self) -> str:
        return repr(self)


class EngineTypeMissing(DriveError):
    """
    Should never happen: the engine used for the given account
    does not exist anymore.
    """

    pass


class FolderAlreadyUsed(DriveError):
    """
    The desired folder to store documents in already used by
    another local account.
    """

    pass


class InvalidSSLCertificate(DriveError):
    """The SSL certificate is not official."""

    def __repr__(self) -> str:
        return "Invalid SSL certificate. Use 'ca-bundle' (or 'ssl-no-verify') option to tune SSL behavior."

    def __str__(self) -> str:
        return repr(self)


class MissingClientSSLCertificate(DriveError):
    """The server needs a client SSL certificate."""

    def __repr__(self) -> str:
        return "No client-side SSL certificate. Use 'cert-file' and 'cert-key-file'."

    def __str__(self) -> str:
        return repr(self)


class MissingXattrSupport(DriveError):
    """
    The desired folder to store documents is located on a filesystem
    that does not support extended attributes.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def __repr__(self) -> str:
        return f"{str(self.path)!r} is located on a filesystem that does not support extended attributes."

    def __str__(self) -> str:
        return repr(self)


class EncryptedSSLCertificateKey(DriveError):
    """The client SSl certificate is encrypted."""

    def __repr__(self) -> str:
        return "Client-side SSL certificate key is encrypted. Please use an unencrypted key with 'cert-key-file'."

    def __str__(self) -> str:
        return repr(self)


class NoAssociatedSoftware(OSError):
    """
    The local file cannot be opened as there is no associated software installed.
    """

    def __init__(self, file_path: Path) -> None:
        from nuxeo.utils import guess_mimetype

        self.filename = file_path.name
        self.mimetype = guess_mimetype(file_path)

    def __repr__(self) -> str:
        return (
            f"There is currently no associated software to open the file {self.filename}. "
            "Please install an appropriate software that can handle files with the mimetype "
            f"{self.mimetype!r} and retry."
        )

    def __str__(self) -> str:
        return repr(self)


class NotFound(OSError):
    """
    A remote document is not found on the server
    or a local file/folder does not exist.
    """

    pass


class ParentNotSynced(ValueError):
    """Fired when the parent folder of a document is not yet synchronized."""

    def __init__(self, local_path: str, local_parent_path: str, /) -> None:
        self.local_path = local_path
        self.local_parent_path = local_parent_path

    def __repr__(self) -> str:
        return (
            f"Parent folder of {self.local_path!r}, {self.local_parent_path!r} "
            "is not bound to a remote folder"
        )

    def __str__(self) -> str:
        return repr(self)


class PairInterrupt(DriveError):
    """There was an error while processing a document pair."""

    pass


class RootAlreadyBindWithDifferentAccount(DriveError):
    """The bound folder is already used by another account."""

    def __init__(self, username: str, url: str, /) -> None:
        self.username = username
        self.url = url


class ScrollDescendantsError(DriveError):
    """Raised when NuxeoDrive.ScrollDescendants returns something we cannot work with."""

    def __init__(self, response: Any, /) -> None:
        self.response = response

    def __repr__(self) -> str:
        return f"ScrollDescendants returned a bad value: {self.response!r}"

    def __str__(self) -> str:
        return repr(self)


class StartupPageConnectionError(DriveError):
    """The web login page is not available."""

    pass


class TransferCancelled(DriveError):
    """A transfer has been cancelled, the file's processing should stop."""

    def __init__(self, transfer_id: int, /) -> None:
        self.transfer_id = transfer_id


class TransferPaused(DriveError):
    """A transfer has been paused, the file's processing should stop."""

    def __init__(self, transfer_id: int, /) -> None:
        self.transfer_id = transfer_id


class DownloadPaused(TransferPaused):
    """A download has been paused, the file's processing should stop."""

    pass


class UploadPaused(TransferPaused):
    """An upload has been paused, the file's processing should stop."""

    pass


class UploadCancelled(TransferCancelled):
    """An upload has been cancelled, the file's processing should stop."""

    pass


class UnknownDigest(ValueError):
    """The digest doesn't fit any known algorithms."""

    def __init__(self, digest: str, /) -> None:
        self.digest = digest

    def __repr__(self) -> str:
        return f"Unknown digest {self.digest!r}"

    def __str__(self) -> str:
        return repr(self)


class UnknownPairState(ValueError):
    """The local and remote state don't fit any pair state."""

    def __init__(self, local_state: str, remote_state: str, /) -> None:
        self.local_state = local_state
        self.remote_state = remote_state

    def __repr__(self) -> str:
        return f"Unknown pair state for {self.local_state!r} and {self.remote_state!r}"

    def __str__(self) -> str:
        return repr(self)


class ThreadInterrupt(DriveError):
    """The worker has been ordered to stop and quit."""

    pass
