# coding: utf-8


class DriveError(Exception):
    """ Mother exception. """
    pass


class DuplicationDisabledError(ValueError):
    """
    Exception raised when de-duplication is disabled and there is a
    file collision.
    """
    pass


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


class InvalidDriveException(DriveError):
    """ The bound folder cannot be used on this gile system. """
    pass


class NotFound(OSError):
    """
    A remote document is not found on the server
    or a local file/folder does not exist.
    """
    pass


class ParentNotSynced(ValueError):
    """ Fired when the parent folder of a document is not yet synchronized. """

    def __init__(self, local_path: str, local_parent_path: str) -> None:
        self.local_path = local_path
        self.local_parent_path = local_parent_path

    def __repr__(self) -> str:
        return "Parent folder of %r, %r is not bound to a remote folder" % (
            self.local_path,
            self.local_parent_path,
        )

    def __str__(self) -> str:
        return repr(self)


class PairInterrupt(DriveError):
    """ There was an error while processing a document pair. """
    pass


class RootAlreadyBindWithDifferentAccount(DriveError):
    """ The bound folder is already used by another account. """

    def __init__(self, username: str, url: str) -> None:
        self.username = username
        self.url = url


class ThreadInterrupt(DriveError):
    """ The worker has been ordered to stop and quit."""
    pass