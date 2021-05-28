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
from typing import Any, Callable, Dict, Set, Tuple, Union
from uuid import uuid4

from . import __version__
from .feature import DisabledFeatures, Feature

__all__ = ("Options",)

log = logging.getLogger(__name__)


# True if the current version is considered alpha
_IS_ALPHA = __version__.count(".") != 2

# Current state of the application (supports only PyInstaller)
_IS_FROZEN = hasattr(sys, "frozen")

# Determine desired defaults for logging level
DEFAULT_LOG_LEVEL_CONSOLE = "WARNING"
DEFAULT_LOG_LEVEL_FILE = "DEBUG" if _IS_ALPHA or not _IS_FROZEN else "INFO"


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
    path = Path(getattr(sys, "_MEIPASS")) if _IS_FROZEN else Path(__file__).parent
    return path / "data"


def _is_system_wide() -> bool:
    return (
        sys.platform == "win32"
        and Path(sys.executable).with_name("system-wide.txt").is_file()
    )


class CallableFeatureHandler:
    """
    All features callbacks in Options will be an instance of this object.

    This object is callable like a function as it implement the __call__() method.

    Each CallableFeatureHandler has a the following private members:

    - feature: the Feature attribute that is to be updated

    Usage example:
        >>> callable = CallableFeatureHandler("feature_name")
        >>> callable(False)  # Features.feature_name will be updated to False

    Notes:
        - callable(arg1) is a shorthand for callable.__call__(arg1)

    """

    def __init__(self, feature: str, /) -> None:
        self._feature = feature

    def __call__(self, new_value: bool, /) -> bool:
        """
        Method called by default when calling the object as a function.
        Update the Feature attribute with the new value.
        Return True if the value has been updated.
        """
        result = False
        if getattr(Feature, self._feature) is not new_value:
            setattr(Feature, self._feature, new_value)
            result = True
        return result


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

    # Document's types where Direct Transfer is forbidden
    __doctypes_no_dt: Tuple[str, ...] = ("Domain", "Section")

    # Setters weight, higher is more powerful
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
        "cert_file": (None, "default"),
        "cert_key_file": (None, "default"),
        "channel": ("centralized", "default"),
        "chunk_limit": (20, "default"),
        "chunk_size": (20, "default"),
        "chunk_upload": (True, "default"),
        "client_version": (None, "default"),
        "custom_metrics": (True, "default"),
        "custom_metrics_poll_interval": (60 * 15, "default"),
        "database_batch_size": (256, "default"),
        "debug": (False, "default"),
        "debug_pydev": (False, "default"),
        "delay": (30, "default"),
        "deletion_behavior": ("unsync", "default"),
        "disabled_file_integrity_check": (False, "default"),
        "disallowed_types_for_dt": (__doctypes_no_dt, "default"),
        "dt_hide_personal_space": (False, "default"),
        "findersync_batch_size": (50, "default"),
        "force_locale": (None, "default"),
        "handshake_timeout": (60, "default"),
        "home": (__home, "default"),
        "ignored_files": (__files, "default"),
        "ignored_prefixes": (__prefixes, "default"),
        "ignored_suffixes": (__suffixes, "default"),
        "is_alpha": (_IS_ALPHA, "default"),
        "is_frozen": (_IS_FROZEN, "default"),
        "light_icons": (False, "default"),
        "locale": ("en", "default"),
        "log_level_console": (DEFAULT_LOG_LEVEL_CONSOLE, "default"),
        "log_level_file": (DEFAULT_LOG_LEVEL_FILE, "default"),
        "max_errors": (3, "default"),
        "nxdrive_home": (__home / ".nuxeo-drive", "default"),
        "nofscheck": (False, "default"),
        "oauth2_authorization_endpoint": (None, "default"),
        "oauth2_client_id": ("nuxeo-drive", "default"),
        "oauth2_client_secret": (None, "default"),
        "oauth2_openid_configuration_url": (None, "default"),
        "oauth2_scope": (None, "default"),
        "oauth2_redirect_uri": ("nxdrive://authorize", "default"),
        "oauth2_token_endpoint": (None, "default"),
        "protocol_url": (None, "default"),
        "proxy_server": (None, "default"),
        "remote_repo": ("default", "default"),
        "res_dir": (_get_resources_dir(), "default"),
        "session_uid": (str(uuid4()), "default"),
        "ssl_no_verify": (False, "default"),
        "startup_page": ("drive_login.jsp", "default"),
        "sync_and_quit": (False, "default"),
        "synchronization_enabled": (False, "default"),
        "system_wide": (_is_system_wide(), "default"),
        "theme": ("ui5", "default"),
        "timeout": (30, "default"),
        "tmp_file_limit": (10.0, "default"),
        "update_check_delay": (3600, "default"),
        "update_site_url": (
            "https://community.nuxeo.com/static/drive-updates",
            "default",
        ),
        "use_analytics": (False, "default"),
        "use_idempotent_requests": (False, "default"),
        "use_sentry": (True, "default"),
    }

    # Add dynamic options from Features
    options.update(
        {
            f"feature_{feature}": (state, "default")
            for feature, state in vars(Feature).items()
        }
    )

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

    def __getattr__(_, item: str, /) -> Any:
        """
        Override to allow retrieving an option as simply as `Options.delay`.
        If the option does not exist, returns `None`.
        """
        try:
            value, _ = MetaOptions.options[item]  # type: ignore
        except KeyError:
            value = None
        return value

    def __setattr__(_, item: str, value: Any, /) -> None:
        """
        Override to allow setting an option as simply as `Options.delay = 42`.
        If the option does not exist, it does nothing.
        Use in tests only.
        """
        with suppress(KeyError):
            MetaOptions.set(item, value, setter="manual")

    def __repr__(_) -> str:
        """Display all options."""
        options = [
            f"{name}[{setter}]={value!r}"
            for name, (value, setter) in MetaOptions.options.items()
        ]
        return f"Options({', '.join(options)})"

    def __str__(_) -> str:
        """Display non default options."""
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
        /,
        *,
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

        # Normalize the option
        item = item.replace("-", "_").replace(".", "_").lower()

        if item.replace("feature_", "") in DisabledFeatures:
            log.warning(f"{item!r} cannot be changed.")
            return

        try:
            old_value, old_setter = MetaOptions.options[item]
        except KeyError:
            if item in MetaOptions.__ignored_options:
                return

            err = f"{item!r} is not a recognized parameter.{src_err}"
            if fail_on_error:
                raise RuntimeError(err)

            log.warning(err)
            return

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

        # Cast path-like options to Path
        if isinstance(old_value, Path):
            # Lazy import to break circular import
            from .utils import normalize_and_expand_path

            new_value = normalize_and_expand_path(new_value)

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
        log.info(f"Option {item!r} updated: {old_value!r} -> {new_value!r} [{setter}]")
        log.info(str(Options))

        # Callback for that option
        callback = MetaOptions.callbacks.get(item)
        if callable(callback):
            callback(new_value)

    @staticmethod
    def update(
        items: Any,
        /,
        *,
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

        callbacks = MetaOptions.callbacks.copy()

        def reinit() -> None:
            setattr(MetaOptions, "callbacks", callbacks)
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
        """Prevent class instances."""
        raise RuntimeError("Instantiation is not allowed.")


#
# Validators
#


def validate_chunk_limit(value: int, /) -> int:
    if value > 0:
        return value
    raise ValueError(f"Chunk limit must be above 0 (got {value!r})")


def validate_chunk_size(value: int, /) -> int:
    if 0 < value <= 1024 * 5:
        return value
    raise ValueError(
        f"Chunk size must be between 1 MiB and 5120 MiB [5 GiB] (got {value!r})"
    )


def validate_client_version(value: str, /) -> str:
    """The minimum version which implements the Centralized channel is 4.2.0,
    downgrades below this version are not allowed.
    """
    from nuxeo.utils import version_lt

    if not version_lt(value, "4.2.0"):
        return value
    raise ValueError(
        f"Downgrade to version {value!r} is not possible. It must be >= '4.2.0'."
    )


def validate_use_sentry(value: bool, /) -> bool:
    if Options.is_frozen and not Options.is_alpha:
        return value
    raise ValueError(
        "Sentry is forcibly enabled on alpha versions or when the app is ran from sources"
    )


def _validate_deletion_behavior(value: str, /) -> str:
    if value in ("unsync", "delete_server"):
        return value
    raise ValueError(f"Unknown deletion behavior {value!r}")


def validate_cert_path(cert_path: str, /) -> str:
    if not Path(cert_path).is_file():
        raise ValueError(f"The file {cert_path!r} does not exist")
    return cert_path


def validate_tmp_file_limit(value: Union[int, float], /) -> float:
    if value > 0:
        return float(value)
    raise ValueError("Temporary file limit must be above 0")


def _callback_synchronization_enabled(new_value: bool) -> None:
    log.warning(
        "The option is deprecated since 5.2.0 and will be removed in a future release."
        " Use 'feature.synchronization' instead."
    )
    setattr(Options, "feature_synchronization", new_value)


# Handler callback for each feature
for feature in vars(Feature).keys():
    Options.callbacks[f"feature_{feature}"] = CallableFeatureHandler(feature)

Options.callbacks["deletion_behavior"] = lambda v: log.info(
    f"Deletion behavior set to {v!r}"
)

Options.callbacks["synchronization_enabled"] = _callback_synchronization_enabled

Options.checkers["chunk_limit"] = validate_chunk_limit
Options.checkers["chunk_size"] = validate_chunk_size
Options.checkers["client_version"] = validate_client_version
Options.checkers["deletion_behavior"] = _validate_deletion_behavior
Options.checkers["use_sentry"] = validate_use_sentry
Options.checkers["tmp_file_limit"] = validate_tmp_file_limit
Options.checkers["cert_file"] = validate_cert_path
Options.checkers["cert_key_file"] = validate_cert_path
