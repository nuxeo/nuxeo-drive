# coding: utf-8
"""
Options management.

The goal is to have a unique object `Options` where the whole configuration
is centralized. Any other part of Drive should use it directly by just
importing the class. No instantiation is needed and therefore it is forbidden.

Using `repr` or `str` on `Options` has different meanings.

    >>> repr(Options)
    Options(delay[default]=30, ...)
    >>> str(Options)
    Options()

`str(Options)` will show only options that are non default (changed by another
configuration):

    >>> Options.set('delay', 42, setter='local')
    >>> Options.set('timeout', -1, setter='server')
    >>> Options.set('locale', 'fr', setter='cli')
    >>> str(Options)
    Options(delay[local]=42, locale[cli]='fr', timeout[server]=-1)

You can access a given option as simply as:

    >>> Options.delay
    30

To set an option, you must call `Options.set` only:

    >>> Options.set('delay', 42)

_For testing purposes_, you can set an option as simply as:

    >>> Options.delay = 42

This is the equivalent of:

    >>> Options.set('delay', 42, setter='manual')

_For testing purposes_, a `Options.mock` decorator is available.

"""

import logging
import sys
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Dict, Set, Optional, Tuple, Union

__all__ = ("Options",)

log = logging.getLogger(__name__)


def _get_freezer() -> Optional[str]:
    """Name of the actual module used to freeze the application."""
    if "__compiled__" in globals():
        return "nuitka"
    elif hasattr(sys, "frozen"):
        return "pyinstaller"
    return None


def _get_frozen_state() -> bool:
    """Find the current state of the application."""
    return _get_freezer() is not None


def _get_home() -> Path:
    """
    Get the user home directory.

    Note about Windows:

        os.path.expanduser("~") and os.getenv("USERPROFILE"|"USERNAME") are not
        trustable when unicode is in the loop. For instance, if the Windows session
        name (i.e. the username) is made of kandjis, everything relying on the
        commands above will fail when packaged with PyInstaller.

        The workaround is to use SHGetFolderPath(), it will return the good value
        whatever characters the path may contain.

        Another idea would be to use the short version of the path, but we will
        try it only if we find bugs with the current implementation.
    """
    path = "~"
    if sys.platform == "win32":
        from win32com.shell import shell, shellcon

        with suppress(Exception):
            path = shell.SHGetFolderPath(0, shellcon.CSIDL_PROFILE, None, 0)

    return Path(path).expanduser().resolve()


def _get_resources_dir() -> Path:
    """Find the resources directory."""
    freezer = _get_freezer()
    if freezer == "nuitka":
        path = Path(__file__).parent
    elif freezer == "pyinstaller":
        path = Path(getattr(sys, "_MEIPASS"))
    else:
        path = Path(__file__).parent
    return path / "data"


def _is_system_wide() -> bool:
    # TODO: check OK with Nuitka
    return (
        sys.platform == "win32"
        and Path(sys.executable).with_name("system-wide.txt").is_file()
    )


class MetaOptions(type):
    """
    All configurable options are used by this lone object.

    Each options is a dict of tuple:

        {
            name: (value, setter),
        }

        - name: option name
        - value: option value
        - setter: which part set it up (the server, the default conf, ...)

    Depending on the setter, the options can or cannot be updated.
    A simple log line will be sent using the logging module.
    """

    # Ignored files, checked lowercase
    __files: Tuple[str] = (r"^atmp\d+$",)  # AutoCAD tmp file

    # Ignored prefixes, checked lowercase
    __prefixes: Tuple[str, ...] = (".", "desktop.ini", "icon\r", "thumbs.db", "~$")

    # Ignored suffixes, checked lowercase
    __suffixes: Tuple[str, ...] = (
        ".bak",
        ".crdownload",
        ".dwl",
        ".dwl2",
        ".idlk",
        ".lnk",
        ".lock",
        ".nxpart",
        ".part",
        ".partial",
        ".swp",
        ".tmp",
        "~",
    )

    # Setters weight, higher is more powerfull
    _setters: Dict[str, int] = {
        "default": 0,
        "server": 1,
        "local": 2,
        "cli": 3,
        "manual": 4,
    }

    # Cache the home directory for later use
    __home: Path = _get_home()

    # Options that should not trigger an error
    __ignored_options: Set[str] = {
        # From the CLI parser
        "command",
        "file",
        "log_filename",
        # From the CLI: bind-server sub-command
        "password",
        "nuxeo_url",
        "local_folder",
        "remote_root",
        "username",
        # From the Manager
        "client_version",
        "light_icons",
        "original_version",
    }

    # Default options
    options: Dict[str, Tuple[Any, str]] = {
        "big_file": (300, "default"),
        "browser_startup_page": ("drive_browser_login.jsp", "default"),
        "ca_bundle": (None, "default"),
        "channel": ("centralized", "default"),
        "chunk_limit": (20, "default"),
        "chunk_size": (20, "default"),
        "chunk_upload": (True, "default"),
        "client_version": (None, "default"),
        "debug": (False, "default"),
        "debug_pydev": (False, "default"),
        "delay": (30, "default"),
        "deletion_behavior": ("unsync", "default"),
        "findersync_batch_size": (50, "default"),
        "force_locale": (None, "default"),
        "freezer": (_get_freezer(), "default"),
        "handshake_timeout": (60, "default"),
        "home": (__home, "default"),
        "ignored_files": (__files, "default"),
        "ignored_prefixes": (__prefixes, "default"),
        "ignored_suffixes": (__suffixes, "default"),
        "is_frozen": (_get_frozen_state(), "default"),
        "locale": ("en", "default"),
        "log_level_console": ("WARNING", "default"),
        "log_level_file": ("INFO", "default"),
        "max_errors": (3, "default"),
        "nxdrive_home": (__home / ".nuxeo-drive", "default"),
        "nofscheck": (False, "default"),
        "protocol_url": (None, "default"),
        "proxy_server": (None, "default"),
        "remote_repo": ("default", "default"),
        "res_dir": (_get_resources_dir(), "default"),
        "ssl_no_verify": (False, "default"),
        "startup_page": ("drive_login.jsp", "default"),
        "sync_and_quit": (False, "default"),
        "synchronization_enabled": (True, "default"),
        "system_wide": (_is_system_wide(), "default"),
        "theme": ("ui5", "default"),
        "timeout": (30, "default"),
        "tmp_file_limit": (10.0, "default"),
        "update_check_delay": (3600, "default"),
        "update_site_url": (
            "https://community.nuxeo.com/static/drive-updates",
            "default",
        ),
        "use_sentry": (True, "default"),
        "use_analytics": (False, "default"),
    }

    default_options = deepcopy(options)

    # Callbacks for the new option's value.
    # It will be called before doing anything to ease value validating.
    # Callable signature must be: (new_value: Any) -> Any
    # It must return the new value, updated or not.
    # To invalidate the new value, raise a ValueError.
    checkers: Dict[str, Callable] = {}

    # Callbacks for any option change.
    # Callable signature must be: (new_value: Any) -> None
    # The return value is not checked.
    callbacks: Dict[str, Callable] = {}

    def __getattr__(cls, item: str) -> Any:
        """
        Override to allow retrieving an option as simply as `Options.delay`.
        If the option does not exist, returns `None`.
        """
        try:
            value, _ = MetaOptions.options[item]
        except KeyError:
            value = None
        return value

    def __setattr__(cls, item: str, value: Any) -> None:
        """
        Override to allow setting an option as simply as `Options.delay = 42`.
        If the option does not exist, it does nothing.
        Use in tests only.
        """
        with suppress(KeyError):
            MetaOptions.set(item, value, setter="manual")

    def __repr__(cls) -> str:
        """ Display all options. """
        options = [
            f"{name}[{setter}]={value!r}"
            for name, (value, setter) in MetaOptions.options.items()
        ]
        return f"Options({', '.join(options)})"

    def __str__(cls) -> str:
        """ Display non default options. """
        options = [
            f"{name}[{setter}]={value!r}"
            for name, (value, setter) in MetaOptions.options.items()
            if setter != "default"
        ]
        return f"Options({', '.join(options)})"

    @staticmethod
    def set(
        item: str,
        new_value: Any,
        setter: str = "default",
        fail_on_error: bool = True,
        file: str = "",
        section: str = "",
    ) -> None:
        """
        Set an option.

        If the option does not exist, if will be ignored if `fail_on_error`
        equals `False`, otherwise `RuntimeError` will be raised.

        If the `setter` has the right to override the option value, set
        `new_value`, else do nothing.

        `file` and `section` are used for a better exception message.

        Any `list` will be converted to a sorted `tuple`.
        And any `tuple` will be appended to the current sequence instead of erasing old values.
        Any `bytes` value will be decoded.

        If the type of the new value differs from the original one,
        raises `TypeError`.  It helps preventing assigning a `str` when
        a `tuple` is required to keep the rest of the code consistent.

        Finally, if a callback is set for that option and if the `new_value`
        is assigned to the option, the callback will be called with the
        `new_value` as sole argument.
        """

        src_err = ""
        if file:
            # There can be a section only when there is a file
            if section:
                src_err = f" From {file!r}, section [{section}]."
            else:
                src_err = f" From {file!r}."

        try:
            old_value, old_setter = MetaOptions.options[item]
        except KeyError:
            if item in MetaOptions.__ignored_options:
                return

            err = f"{item!r} is not a recognized parameter.{src_err}"
            if fail_on_error:
                raise RuntimeError(err)
            else:
                log.warning(err)
        else:
            if isinstance(new_value, list):
                # Need a tuple when JSON sends a simple list
                new_value = tuple(sorted({*old_value, *new_value}))
            elif isinstance(new_value, bytes):
                # No option needs bytes
                new_value = new_value.decode("utf-8")

            # Try implicit conversions. We do not use isinstance to prevent
            # checking against subtypes.
            type_orig = type(old_value)
            if type_orig is bool:
                with suppress(ValueError, TypeError):
                    new_value = bool(new_value)
            elif type_orig is int:
                with suppress(ValueError, TypeError):
                    new_value = int(new_value)

            # Check the new value meets our requirements, if any
            check = MetaOptions.checkers.get(item, None)
            if callable(check):
                try:
                    new_value = check(new_value)
                except ValueError as exc:
                    log.warning(str(exc))
                    log.warning(
                        f"Callback check for {item!r} denied modification."
                        f" Value is still {old_value!r}."
                    )
                    return

            # If the option was set from a local config file, it must be taken into account
            # event if the value is the same as the default one (see NXDRIVE-1980).
            if new_value == old_value and setter not in ("local", "manual"):
                return

            # We allow to set something when the default is None
            if not isinstance(new_value, type_orig) and not isinstance(
                old_value, type(None)
            ):
                err = (
                    f"The type of the {item!r} option is {type(new_value).__name__}, "
                    f"while {type(old_value).__name__} is required.{src_err}"
                )
                if fail_on_error:
                    raise TypeError(err)
                else:
                    log.warning(err)

            # Only update if the setter has rights to
            if MetaOptions._setters[setter] < MetaOptions._setters[old_setter]:
                return

            MetaOptions.options[item] = new_value, setter
            log.info(
                f"Option {item!r} updated: {old_value!r} -> {new_value!r} [{setter}]"
            )
            log.debug(str(Options))

            # Callback for that option
            callback = MetaOptions.callbacks.get(item)
            if callable(callback):
                callback(new_value)

    @staticmethod
    def update(
        items: Any,
        setter: str = "default",
        fail_on_error: bool = True,
        file: str = "",
        section: str = "",
    ) -> None:
        """
        Batch update options.
        If an option does not exist, it will be ignored.
        """

        if isinstance(items, dict):
            # To handle local and server config files
            items = items.items()
        elif not isinstance(items, list):
            # To handle CLI (type is argparse.Namespace)
            items = items._get_kwargs()  # pylint: disable=protected-access

        for item, value in items:
            MetaOptions.set(
                item,
                value,
                setter=setter,
                fail_on_error=fail_on_error,
                file=file,
                section=section,
            )

    @staticmethod
    def mock() -> Callable:
        """
        Decorator for tests.
        It saves initial states, launches the test and restores states then.

            @Options.mock()
            def test_method(self):
                ...

            @Options.mock()
            def test_function():
                ...

        """

        import functools

        def reinit() -> None:
            setattr(MetaOptions, "callbacks", {})
            setattr(MetaOptions, "options", deepcopy(MetaOptions.default_options))

        def decorator(func):  # type: ignore
            @functools.wraps(func)
            def wrapper(*args, **kwargs):  # type: ignore
                try:
                    return func(*args, **kwargs)
                finally:
                    reinit()

            return wrapper

        return decorator


class Options(metaclass=MetaOptions):
    def __init__(self) -> None:
        """ Prevent class instances. """
        raise RuntimeError("Instantiation is not allowed.")


#
# Validators
#


def validate_chunk_limit(value: int) -> int:
    if value > 0:
        return value
    raise ValueError(f"Chunk limit must be above 0 (got {value!r})")


def validate_chunk_size(value: int) -> int:
    if 0 < value <= 20:
        return value
    raise ValueError(f"Chunk size must be between 1 and 20 MiB (got {value!r})")


def validate_client_version(value: str) -> str:
    """The minimum version which implements the Centralized channel is 4.2.0,
    downgrades below this version are not allowed.
    """
    from .utils import version_lt

    if not version_lt(value, "4.2.0"):
        return value
    raise ValueError(
        f"Downgrade to version {value!r} is not possible. It must be >= '4.2.0'."
    )


def validate_tmp_file_limit(value: Union[int, float]) -> float:
    if value > 0:
        return float(value)
    raise ValueError("Temporary file limit must be above 0")


Options.checkers["chunk_limit"] = validate_chunk_limit
Options.checkers["chunk_size"] = validate_chunk_size
Options.checkers["client_version"] = validate_client_version
Options.checkers["tmp_file_limit"] = validate_tmp_file_limit
