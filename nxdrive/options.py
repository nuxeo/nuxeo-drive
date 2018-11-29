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
import os.path
import sys
from contextlib import suppress
from copy import deepcopy
from typing import Any, Callable, Dict, Tuple

__all__ = ("Options",)

log = logging.getLogger(__name__)


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

    def __get_home(*_) -> str:
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
        if sys.platform == "win32":
            from contextlib import suppress
            from win32com.shell import shell, shellcon

            with suppress(Exception):
                return shell.SHGetFolderPath(0, shellcon.CSIDL_PROFILE, None, 0)

        return os.path.expanduser("~")

    # Cache the home directory for later use
    __home: str = __get_home()

    # Default options
    options: Dict[str, Tuple[Any, str]] = {
        "beta_channel": (False, "default"),
        "browser_startup_page": ("drive_browser_login.jsp", "default"),
        "ca_bundle": (None, "default"),
        "debug": (False, "default"),
        "debug_pydev": (False, "default"),
        "delay": (30, "default"),
        "findersync_batch_size": (50, "default"),
        "force_locale": (None, "default"),
        "handshake_timeout": (60, "default"),
        "home": (__home, "default"),
        "ignored_files": (__files, "default"),
        "ignored_prefixes": (__prefixes, "default"),
        "ignored_suffixes": (__suffixes, "default"),
        "is_frozen": (getattr(sys, "frozen", False), "default"),
        "locale": ("en", "default"),
        "log_level_console": ("INFO", "default"),
        "log_level_file": ("DEBUG", "default"),
        "max_errors": (3, "default"),
        "max_sync_step": (10, "default"),
        "nxdrive_home": (os.path.join(__home, ".nuxeo-drive"), "default"),
        "nofscheck": (False, "default"),
        "protocol_url": (None, "default"),
        "proxy_server": (None, "default"),
        "remote_repo": ("default", "default"),
        "res_dir": (
            os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(__file__)), "data"),
            "default",
        ),
        "ssl_no_verify": (False, "default"),
        "startup_page": ("drive_login.jsp", "default"),
        "system_wide": (
            sys.platform == "win32"
            and os.path.isfile(
                os.path.join(os.path.dirname(sys.executable), "system-wide.txt")
            ),
            "default",
        ),
        "theme": ("ui5", "default"),
        "timeout": (30, "default"),
        "update_check_delay": (3600, "default"),
        "update_site_url": (
            "https://community.nuxeo.com/static/drive-updates",
            "default",
        ),
    }

    default_options = deepcopy(options)

    # Callbacks for any option change.
    # Callable signature must be: (new_value: str) -> None
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
            if fail_on_error:
                raise RuntimeError(
                    f"{item!r} is not a recognized parameter.{src_err}"
                ) from None
        else:
            if isinstance(new_value, list):
                # Need a tuple when JSON sends a simple list
                new_value = tuple(sorted(new_value))
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

            if new_value == old_value:
                return

            # We allow to set something when the default is None
            if not isinstance(new_value, type_orig) and not isinstance(
                old_value, type(None)
            ):
                if not fail_on_error:
                    return

                err = (
                    f"The type of the {item!r} option is {type(new_value).__name__}, "
                    f"while {type(old_value).__name__} is required.{src_err}"
                )
                raise TypeError(err)

            # Only update if the setter has rights to
            setter = setter.lower()
            if MetaOptions._setters[setter] >= MetaOptions._setters[old_setter]:
                MetaOptions.options[item] = new_value, setter
                log.debug(
                    f"Option {item!r} updated: {old_value!r} -> {new_value!r} [{setter}]"
                )

                # Callback for that option
                with suppress(KeyError):
                    callback = MetaOptions.callbacks[item]
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
            items = items._get_kwargs()

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

        def reinit():
            setattr(MetaOptions, "callbacks", {})
            setattr(MetaOptions, "options", deepcopy(MetaOptions.default_options))

        def decorator(func):
            def wrapper(*args, **kwargs):
                reinit()
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
