""" Utilities to operate Nuxeo Drive from the command line. """

import faulthandler
import os
import sys
from argparse import ArgumentParser, Namespace
from configparser import DEFAULTSECT, ConfigParser
from datetime import datetime
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from . import __version__
from .constants import APP_NAME, BUNDLE_IDENTIFIER, DEFAULT_CHANNEL, LINUX
from .logging_config import configure
from .options import DEFAULT_LOG_LEVEL_CONSOLE, DEFAULT_LOG_LEVEL_FILE, Options
from .osi import AbstractOSIntegration
from .state import State
from .utils import (
    config_paths,
    force_encode,
    get_default_local_folder,
    get_value,
    normalize_and_expand_path,
    normalized_path,
)

try:
    from .qt.imports import QSslSocket
except ImportError:
    QSslSocket = None

if TYPE_CHECKING:
    from .gui.application import Application  # noqa
    from .console import ConsoleApplication  # noqa
    from .manager import Manager  # noqa

__all__ = ("CliHandler",)

log = getLogger(__name__)

USAGE = """ndrive [command]

If no command is provided, the graphical application is
started along with a synchronization process.

Possible commands:
- access-online
- bind-root
- bind-server
- clean-folder
- console
- copy-share-link
- direct-transfer
- edit-metadata
- unbind-root
- unbind-server

To get options for a specific command:

  ndrive command --help

"""
DEFAULT_LOCAL_FOLDER = get_default_local_folder()


class CliHandler:
    """Set default arguments."""

    def get_version(self) -> str:
        return __version__

    def make_cli_parser(self, *, add_subparsers: bool = True) -> ArgumentParser:
        """
        Parse commandline arguments using a git-like subcommands scheme.
        """

        common_parser = ArgumentParser(add_help=False)
        common_parser.add_argument(
            "--nxdrive-home",
            default=Options.nxdrive_home,
            help=f"Folder to store the {APP_NAME} configuration",
        )

        common_parser.add_argument(
            "--log-level-file",
            default=DEFAULT_LOG_LEVEL_FILE,
            choices=("DEBUG", "INFO", "WARNING", "ERROR"),
            help="Minimum log level for the file log",
        )

        common_parser.add_argument(
            "--log-level-console",
            default=DEFAULT_LOG_LEVEL_CONSOLE,
            choices=("DEBUG", "INFO", "WARNING", "ERROR"),
            help="Minimum log level for the console log",
        )

        common_parser.add_argument("--log-filename", help="File used to store the logs")

        common_parser.add_argument(
            "--locale", default=Options.locale, help="Select the default language"
        )

        common_parser.add_argument("--force-locale", help="Force the language")

        common_parser.add_argument(
            "--update-site-url",
            default=Options.update_site_url,
            help="Website for client auto-update",
        )

        common_parser.add_argument(
            "--channel",
            default=DEFAULT_CHANNEL,
            choices=("alpha", "beta", "release", "centralized"),
            help="Update channel",
        )

        common_parser.add_argument(
            "--debug",
            default=Options.debug,
            action="store_true",
            help="Fire a debugger one uncaught error and enable REST API parameter checks.",
        )

        common_parser.add_argument(
            "--nofscheck",
            default=Options.nofscheck,
            action="store_true",
            help="Disable the standard check for binding, to allow installation on network filesystem.",
        )

        common_parser.add_argument("--proxy-server", help="Define proxy server")

        common_parser.add_argument(
            "--ssl-no-verify",
            default=Options.ssl_no_verify,
            action="store_true",
            help="Allows invalid/custom certificates. Highly unadvised to enable this option.",
        )

        common_parser.add_argument(
            "--sync-and-quit",
            default=Options.sync_and_quit,
            action="store_true",
            help="Launch the synchronization and then exit the application.",
        )

        common_parser.add_argument(
            "--debug-pydev",
            default=Options.debug_pydev,
            action="store_true",
            help="Allow debugging with a PyDev server",
        )

        common_parser.add_argument(
            "--delay",
            default=Options.delay,
            type=int,
            help="Delay in seconds for remote polling",
        )

        common_parser.add_argument(
            "--handshake-timeout",
            default=Options.handshake_timeout,
            type=int,
            help="HTTP request timeout in seconds for the handshake",
        )

        common_parser.add_argument(
            "--timeout",
            default=Options.timeout,
            type=int,
            help="HTTP request timeout in seconds for sync Automation call",
        )

        common_parser.add_argument(
            "--update-check-delay",
            default=Options.update_check_delay,
            type=int,
            help="Delay in seconds between checks for application update",
        )

        common_parser.add_argument(
            "--max-errors",
            default=Options.max_errors,
            type=int,
            help="Maximum number of tries before giving up synchronization of "
            "a file in error",
        )

        common_parser.add_argument(
            "-v",
            "--version",
            action="version",
            version=self.get_version(),
            help=f"Print the current version of the {APP_NAME} client",
        )

        parser = ArgumentParser(
            parents=[common_parser],
            description=f"Command line interface for {APP_NAME} operations.",
            usage=USAGE,
        )

        if not add_subparsers:
            return parser

        subparsers = parser.add_subparsers(title="Commands")

        # Link to a remote Nuxeo server
        bind_server_parser = subparsers.add_parser(
            "bind-server",
            help="Attach a local folder to a Nuxeo server.",
            parents=[common_parser],
        )
        bind_server_parser.set_defaults(command="bind_server")
        bind_server_parser.add_argument(
            "--password", help="Password for the Nuxeo account"
        )
        bind_server_parser.add_argument(
            "--local-folder",
            help="Local folder that will host the list of synchronized "
            "workspaces with a remote Nuxeo server.",
            default=DEFAULT_LOCAL_FOLDER,
        )
        bind_server_parser.add_argument(
            "username", help="User account to connect to Nuxeo"
        )
        bind_server_parser.add_argument("nuxeo_url", help="URL of the Nuxeo server.")
        bind_server_parser.add_argument(
            "--remote-repo",
            default=Options.remote_repo,
            help="Name of the remote repository.",
        )

        # Unlink from a remote Nuxeo server
        unbind_server_parser = subparsers.add_parser(
            "unbind-server",
            help="Detach from a remote Nuxeo server.",
            parents=[common_parser],
        )
        unbind_server_parser.set_defaults(command="unbind_server")
        unbind_server_parser.add_argument(
            "--local-folder",
            help="Local folder that hosts the list of synchronized "
            "workspaces with a remote Nuxeo server.",
            type=str,
            default=DEFAULT_LOCAL_FOLDER,
        )

        # Bind root folders
        bind_root_parser = subparsers.add_parser(
            "bind-root",
            help="Register a folder as a synchronization root.",
            parents=[common_parser],
        )
        bind_root_parser.set_defaults(command="bind_root")
        bind_root_parser.add_argument(
            "remote_root",
            help="Remote path or id reference of a folder to synchronize.",
        )
        bind_root_parser.add_argument(
            "--local-folder",
            help="Local folder that will host the list of synchronized "
            "workspaces with a remote Nuxeo server. Must be bound with the "
            '"bind-server" command.',
            default=DEFAULT_LOCAL_FOLDER,
        )
        bind_root_parser.add_argument(
            "--remote-repo",
            default=Options.remote_repo,
            help="Name of the remote repository.",
        )

        # Unlink from a remote Nuxeo root
        unbind_root_parser = subparsers.add_parser(
            "unbind-root",
            help="Unregister a folder as a synchronization root.",
            parents=[common_parser],
        )
        unbind_root_parser.set_defaults(command="unbind_root")

        unbind_root_parser.add_argument(
            "remote_root",
            help="Remote path or id reference of a folder to synchronize.",
        )
        unbind_root_parser.add_argument(
            "--local-folder",
            help="Local folder that will host the list of synchronized "
            "workspaces with a remote Nuxeo server. Must be bound with the "
            '"bind-server" command.',
            default=DEFAULT_LOCAL_FOLDER,
        )
        unbind_root_parser.add_argument(
            "--remote-repo",
            default=Options.remote_repo,
            help="Name of the remote repository.",
        )

        # Uninstall
        uninstall_parser = subparsers.add_parser(
            "uninstall", help="Remove app data", parents=[common_parser]
        )
        uninstall_parser.set_defaults(command="uninstall")

        # Run in console mode
        console_parser = subparsers.add_parser(
            "console", help="Start in GUI-less mode.", parents=[common_parser]
        )
        console_parser.set_defaults(command="console")

        # Clean the folder
        clean_parser = subparsers.add_parser(
            "clean-folder",
            help="Remove recursively extended attributes from a given folder.",
            parents=[common_parser],
        )
        clean_parser.add_argument("--local-folder", help="Local folder to clean.")
        clean_parser.set_defaults(command="clean_folder")

        # Context menu: Access online
        ctx_item1 = subparsers.add_parser(
            "access-online",
            help="Open the document in the browser.",
            parents=[common_parser],
        )
        ctx_item1.set_defaults(command="ctx_access_online")
        ctx_item1.add_argument("--file", default="", help="File path.")

        # Context menu: Copy the share-link
        ctx_item2 = subparsers.add_parser(
            "copy-share-link",
            help="Copy the document's share-link to the clipboard.",
            parents=[common_parser],
        )
        ctx_item2.set_defaults(command="ctx_copy_share_link")
        ctx_item2.add_argument("--file", default="", help="File path.")

        # Context menu: Edit metadata
        ctx_item3 = subparsers.add_parser(
            "edit-metadata",
            help="Display the metadata window for a given file.",
            parents=[common_parser],
        )
        ctx_item3.set_defaults(command="ctx_edit_metadata")
        ctx_item3.add_argument("--file", default="", help="File path.")

        # Context menu: Direct Transfer
        ctx_item4 = subparsers.add_parser(
            "direct-transfer",
            help="Direct Transfer of a given file to anywhere on the server.",
            parents=[common_parser],
        )
        ctx_item4.set_defaults(command="ctx_direct_transfer")
        ctx_item4.add_argument("--file", default="", help="File path.")

        return parser

    """Command Line Interface handler: parse options and execute operation"""

    def parse_cli(self, argv: List[str], /) -> Namespace:
        """Parse the command line argument using argparse and protocol URL"""
        # Filter psn argument provided by OSX .app service launcher
        # https://developer.apple.com/library/mac/documentation/Carbon/Reference/LaunchServicesReference/LaunchServicesReference.pdf
        # When run from the .app bundle generated with py2app with
        # argv_emulation=True this is already filtered out but we keep it
        # for running CLI from the source folder in development.
        argv = [a for a in argv if not a.startswith("-psn_")]

        # Preprocess the args to detect protocol handler calls and be more
        # tolerant to missing subcommand
        has_command = False

        filtered_args = []
        for arg in argv:
            if arg.startswith("nxdrive://"):
                Options.set("protocol_url", arg, setter="cli")
                continue
            if not arg.startswith("-"):
                has_command = True
            filtered_args.append(arg)

        parser = self.make_cli_parser(add_subparsers=has_command)

        # Change default value according to config.ini
        args = self.load_config()
        if args:
            parser.set_defaults(**args)
        options = parser.parse_args(filtered_args)

        if options.debug:
            import threading
            from traceback import print_exception
            from types import TracebackType
            from typing import Type

            try:
                import ipdb
            except ImportError:
                import pdb
            else:
                pdb = ipdb

            # Automatically check all operations done with the Python client
            import nuxeo.constants

            nuxeo.constants.CHECK_PARAMS = True

            # Install Post-Mortem debugger hook

            def excepthook(
                type_: Type[BaseException],
                value: BaseException,
                traceback: TracebackType,
            ) -> None:
                print_exception(type_, value, traceback)
                pdb.pm()

            sys.excepthook = excepthook

            def texcepthook(args: Any) -> None:
                print_exception(args.exc_type, args.exc_value, args.exc_traceback)
                pdb.pm()

            threading.excepthook = texcepthook

        return options

    def _load_local_config(
        self, sources: Tuple[Path, ...], args: Dict[str, Any]
    ) -> None:
        """
        Load local configuration from different *sources*.
        Each configuration file is independent and can define its own `env` section.
        """
        for conf_file in sources:
            if not conf_file.is_file():
                continue

            config = ConfigParser()
            log.info(f"Reading local configuration file {str(conf_file)!r} ...")
            with conf_file.open(encoding="utf-8") as fh:
                try:
                    config.read_file(fh)
                except Exception:
                    log.warning("Skipped malformed file", exc_info=True)
                    continue

            if not config.has_option(DEFAULTSECT, "env"):
                log.warning(
                    f"The [{DEFAULTSECT}] section is not present, skipping the file"
                )
                continue

            env = config.get(DEFAULTSECT, "env")
            conf_args = {}

            for name, value in config.items(env):
                if name == "env" or value == "":
                    continue

                # Normalize the key
                name = name.replace("-", "_").replace(".", "_").lower()
                conf_args[name] = get_value(value)

            if conf_args:
                file = os.path.abspath(conf_file)
                Options.update(conf_args, setter="local", file=file, section=env)
                args.update(**conf_args)

    def load_config(self) -> Dict[str, Any]:
        """
        Load local configuration from different sources:
            - the registry on Windows
            - config.ini next to the current executable
            - config.ini from the ~/.nuxeo-drive folder
            - config.ini from the current working directory
        Each configuration file is independent and can define its own `env` section.
        """
        args = AbstractOSIntegration.get(None).get_system_configuration()
        if args:
            # This is the case on Windows only, values from the registry
            Options.update(args, setter="local", file="the Registry")

        # Load local configs
        paths, _ = config_paths()
        current_nxdrive_home = Options.nxdrive_home
        self._load_local_config(paths, args)

        # To ensure options are well respected, as nxdrive_home were updated in the
        # original config file, we need to rescan for config files into the new folder.
        # See NXDRIVE-2631 for more details.
        if current_nxdrive_home != Options.nxdrive_home:
            _, path = config_paths()
            self._load_local_config((path,), args)

        return args

    def _configure_logger(self, command: str, options: Namespace, /) -> None:
        """Configure the logging framework from the provided options."""

        # Ensure the log folder exists
        folder_log = os.path.join(options.nxdrive_home, "logs")
        os.makedirs(folder_log, exist_ok=True)

        filename = options.log_filename
        if not filename:
            filename = os.path.join(folder_log, "nxdrive.log")

        configure(
            log_filename=filename,
            file_level=options.log_level_file,
            console_level=options.log_level_console,
            command_name=command,
            force_configure=True,
        )

    def uninstall(self, options: Optional[Namespace], /) -> None:
        AbstractOSIntegration.get(None).uninstall()

    def handle(self, argv: List[str], /) -> int:
        """Parse options, setup logs and manager and dispatch execution."""

        # Pre-configure the logging to catch early errors
        early_options = Namespace(
            log_filename="",
            log_level_console="INFO",
            log_level_file="DEBUG",
            nxdrive_home=Options.nxdrive_home,
        )
        self._configure_logger("early", early_options)

        options = self.parse_cli(argv)

        if hasattr(options, "local_folder"):
            options.local_folder = normalize_and_expand_path(options.local_folder)
        if hasattr(options, "nxdrive_home"):
            options.nxdrive_home = normalize_and_expand_path(options.nxdrive_home)

        command = getattr(options, "command", "launch")
        handler = getattr(self, command, None)
        if not handler:
            raise RuntimeError(f"No handler implemented for command {command}")

        self._configure_logger(command, options)

        log.info(f"Command line: argv={argv!r}, options={options!r}")
        log.info(f"Running on version {self.get_version()}")

        # We cannot use fail_on_error=True because options is a namespace
        # and contains a lot of nonexistent Options values.
        Options.update(options, setter="cli", fail_on_error=False)

        if QSslSocket:
            has_ssl_support = QSslSocket.supportsSsl()
            log.info(f"SSL support: {has_ssl_support!r}")
            if not has_ssl_support:
                # If the option --ssl-no-verify is True, then we do not care about SSL support
                # We also do not block GNU/Linux users as it may not work properly (Ubutun 14.04 for instance)
                if Options.is_frozen and not Options.ssl_no_verify and not LINUX:
                    raise RuntimeError("No SSL support, packaging must have failed.")

                log.warning("No SSL support! HTTPS validation will be skipped.")
                options.ca_bundle = None
                options.cert_file = None
                options.cert_key_file = None
                options.ssl_no_verify = True

        if command != "uninstall":
            self._install_faulthandler()
            self.manager = self.get_manager()

        ret_code: int = handler(options)
        return ret_code

    def get_manager(self) -> "Manager":
        from .manager import Manager  # noqa

        return Manager(Options.nxdrive_home)

    def _get_application(
        self, *, console: bool = False
    ) -> Union["Application", "ConsoleApplication"]:
        if console:
            from .console import ConsoleApplication as Application  # noqa
        else:
            from .gui.application import Application  # noqa
            from .gui.systray import SystrayWindow
            from .qt.imports import qmlRegisterType

            qmlRegisterType(SystrayWindow, "SystrayWindow", 1, 0, "SystrayWindow")
        return Application(self.manager)

    def launch(self, options: Optional[Namespace], /, *, console: bool = False) -> int:
        """Launch the Qt app in the main thread and sync in another thread."""
        from .utils import PidLockFile

        lock = PidLockFile(self.manager.home, "qt")
        pid = lock.lock()
        if pid:
            if Options.protocol_url:
                payload = force_encode(Options.protocol_url)
                self._send_to_running_instance(payload, pid)
            else:
                log.warning(f"{APP_NAME} is already running: exiting.")
            return 0

        exit_code: int = 1
        with HealthCheck():
            # Monitor the "minimum syndical".
            # If a crash happens outside that context manager, this is not considered a crash
            # as we only do care about synchronization parts that could be altered.
            app = self._get_application(console=console)
            exit_code = app.exec_()

        lock.unlock()
        log.info(f"{APP_NAME} exited with code {exit_code}")
        return exit_code

    def redact_payload(self, payload: bytes, /) -> bytes:
        """Some information may not be needed in logs."""

        # Do not disclose the token in logs
        if payload.startswith(b"nxdrive://token/"):
            payload = b"<REDACTED>"

        return payload

    def _send_to_running_instance(self, payload: bytes, pid: int, /) -> None:
        from .qt import constants as qt
        from .qt.imports import QByteArray, QLocalSocket

        named_pipe = f"{BUNDLE_IDENTIFIER}.protocol.{pid}"
        log.debug(
            f"Opening a local socket to the running instance on {named_pipe} "
            f"(payload={self.redact_payload(payload)!r})"
        )
        client = QLocalSocket()
        try:
            client.connectToServer(named_pipe)

            if not client.waitForConnected():
                log.error(f"Unable to open client socket: {client.errorString()}")
                return

            client.write(QByteArray(payload))
            client.waitForBytesWritten()
            client.disconnectFromServer()
            if client.state() == qt.ConnectedState:
                client.waitForDisconnected()
        finally:
            del client
        log.debug("Successfully closed client socket")

    def clean_folder(self, options: Namespace, /) -> int:
        from .client.local import LocalClient

        if not options.local_folder:
            print("A folder must be specified")
            return 1

        client = LocalClient(options.local_folder)
        client.clean_xattr_root()
        return 0

    def console(self, options: Namespace, /) -> int:
        if options.debug_pydev:
            from pydev import pydevd

            pydevd.settrace()
        return self.launch(options, console=True)

    def ctx_access_online(self, options: Namespace, /) -> None:
        """Event fired by "Access online" menu entry."""
        file_path = normalized_path(options.file)
        self.manager.ctx_access_online(file_path)

    def ctx_copy_share_link(self, options: Namespace, /) -> None:
        """Event fired by "Copy share-link" menu entry."""
        file_path = normalized_path(options.file)
        self.manager.ctx_copy_share_link(file_path)

    def ctx_edit_metadata(self, options: Namespace, /) -> None:
        """Event fired by "Edit metadata" menu entry."""
        file_path = normalized_path(options.file)
        self.manager.ctx_edit_metadata(file_path)

    def ctx_direct_transfer(self, options: Namespace, /) -> int:
        """Event fired by "Direct Transfer" menu entry."""
        # Craft the URL to be handled later at application startup
        Options.protocol_url = f"nxdrive://direct-transfer/{options.file}"
        self.launch(options)
        return 0

    def download_edit(self, options: Namespace, /) -> int:
        self.launch(options)
        return 0

    def bind_server(self, options: Namespace, /) -> int:
        password, check_credentials = "", True
        if not options.password:
            check_credentials = False
        else:
            password = options.password
        if not options.local_folder:
            options.local_folder = DEFAULT_LOCAL_FOLDER

        self.manager.bind_server(
            options.local_folder,
            options.nuxeo_url,
            options.username,
            password=password,
            start_engine=False,
            check_credentials=check_credentials,
        )
        return 0

    def unbind_server(self, options: Namespace, /) -> int:
        for uid, engine in self.manager.engines.copy().items():
            if engine.local_folder == options.local_folder:
                self.manager.unbind_engine(uid)
                return 0
        log.warning(f"No engine registered for local folder {options.local_folder!r}")
        return 1

    def bind_root(self, options: Namespace, /) -> int:
        for engine in self.manager.engines.copy().values():
            if engine.local_folder == options.local_folder:
                engine.remote.register_as_root(options.remote_root)
                return 0
        log.warning(f"No engine registered for local folder {options.local_folder!r}")
        return 1

    def unbind_root(self, options: Namespace, /) -> int:
        for engine in self.manager.engines.copy().values():
            if engine.local_folder == options.local_folder:
                engine.remote.unregister_as_root(options.remote_root)
                return 0
        log.warning(f"No engine registered for local folder {options.local_folder!r}")
        return 1

    @staticmethod
    def _install_faulthandler() -> None:
        """Utility to help debug segfaults."""
        segfault_filename = Options.nxdrive_home / "logs" / "segfault.log"
        log.info(f"Enabling faulthandler in {segfault_filename!r}")

        with segfault_filename.open(mode="a", encoding="utf-8") as fh:
            fh.write(f"\n\n\n>>> {datetime.now()}\n")
            faulthandler.enable(file=fh)


class HealthCheck:
    """
    Simple class to be used as a context manager to manage a "crash" file
    helping to know if the application previously crashed.

    File handling and clean-up are automatic.
    """

    def __init__(self, folder: Optional[Path] = None) -> None:
        """Allow to pass a custom *folder* to ease testing."""
        # Note1: do not rely on Options.nxdrive_home as it may be changed in options.
        # Note2: keep that code synced with fatal_error.py::`show_critical_error()`.
        folder = folder or Path.home() / ".nuxeo-drive"
        folder.mkdir(parents=True, exist_ok=True)
        self.crash_file = folder / "crash.state"

    def __enter__(self) -> "HealthCheck":
        """Get or create the crash file to know the current application's state."""
        # Be careful for any error, so using a broad try/catch block.
        try:
            try:
                State.crash_details = self.crash_file.read_text(
                    encoding="utf-8", errors="ignore"
                )
            except FileNotFoundError:
                # Create the file for the next run
                self.crash_file.touch()
            else:
                log.warning("It seems the application crashed at the previous run 😮")
                log.warning(f"Crash trace:\n{State.crash_details}")
                State.has_crashed = True
        except Exception:
            log.exception("Cannot get or create the crash file")

        return self

    def __exit__(self, *_: Any) -> None:
        """
        Clean the crash file as everything went well.
        This code would unlikely being called on a hard crash and so the clean-up
        would not be done.
        """
        # Be careful for any error, so using a broad try/catch block.
        try:
            self.crash_file.unlink(missing_ok=True)
        except Exception:
            log.exception("Cannot clean-up the crash file")
