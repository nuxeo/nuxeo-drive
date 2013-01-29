import os


def normalized_path(path):
    """Return absolute, normalized file path"""
    # XXX: we could os.path.normcase as well under Windows but it might be the
    # source of unexpected troubles so no doing it for now.

    # We do not expand the user folder marker `~` as we expect the OS shell to
    # do it automatically when using the commandline or we do it explicitly
    # where appropriate
    return os.path.normpath(os.path.abspath(path))
