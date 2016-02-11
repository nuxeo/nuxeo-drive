"""Utilities to operate Nuxeo Drive from the command line"""
import os
import sys
import argparse
from getpass import getpass
import traceback
import threading
try:
    import ipdb
    debugger = ipdb
except ImportError:
    import pdb
    debugger = pdb

from nxdrive.client.common import DEFAULT_REPOSITORY_NAME
from nxdrive.osi.daemon import daemonize
from nxdrive.utils import default_nuxeo_drive_folder, normalized_path
from nxdrive.logging_config import configure
from nxdrive.logging_config import get_logger
from nxdrive import __version__


DEFAULT_NX_DRIVE_FOLDER = default_nuxeo_drive_folder()
DEFAULT_MAX_SYNC_STEP = 10
DEFAULT_REMOTE_WATCHER_DELAY = 30
DEFAULT_QUIT_TIMEOUT = -1
DEFAULT_HANDSHAKE_TIMEOUT = 60
DEFAULT_TIMEOUT = 20
DEFAULT_UPDATE_CHECK_DELAY = 3600
DEFAULT_MAX_ERRORS = 3
DEFAULT_UPDATE_SITE_URL = 'http://community.nuxeo.com/static/drive/'
USAGE = """ndrive [command]

If no command is provided, the graphical application is started along with a
synchronization process.

Possible commands:
- console
- bind-server
- unbind-server
- bind-root
- unbind-root
- clean_folder
- metadata

To get options for a specific command:

  ndrive command --help

"""

PROTOCOL_COMMANDS = {
    'nxdriveedit': 'edit',
    'nxdrivebind': 'bind_server',
}
GET_CTL_MAX_NB_TRIES = 5
GET_CTL_SLEEP_DURATION = 1


class CliHandler(object):
    """ Set the default argument """
    def __init__(self):
        self.default_home = os.path.join('~', '.nuxeo-drive')
        self.default_log_console_level = "INFO"
        self.default_remote_watcher_delay = DEFAULT_REMOTE_WATCHER_DELAY
        self.default_max_sync_step = DEFAULT_MAX_SYNC_STEP
        self.default_handshake_timeout = DEFAULT_HANDSHAKE_TIMEOUT
        self.default_timeout = DEFAULT_TIMEOUT
        self.default_stop_on_error = True
        self.default_max_errors = DEFAULT_MAX_ERRORS

    def get_version(self):
        return __version__

    def make_cli_parser(self, add_subparsers=True):
        """Parse commandline arguments using a git-like subcommands scheme"""
        common_parser = argparse.ArgumentParser(
            add_help=False,
        )
        common_parser.add_argument(
            "--nxdrive-home",
            default=self.default_home,
            help="Folder to store the Nuxeo Drive configuration."
        )
        common_parser.add_argument(
            "--log-level-file",
            help="Minimum log level for the file log"
                        " (under NXDRIVE_HOME/logs)."
        )
        common_parser.add_argument(
            "--log-level-console",
            default=self.default_log_console_level,
            help="Minimum log level for the console log."
        )
        common_parser.add_argument(
            "--log-filename",
            help=("File used to store the logs, default "
                  "NXDRIVE_HOME/logs/nxaudit.logs")
        )
        common_parser.add_argument(
            "--locale",
            help=("Select the default language")
        )
        common_parser.add_argument(
            "--force-locale",
            help=("Force the language")
        )
        common_parser.add_argument(
            "--update-site-url",
            default=DEFAULT_UPDATE_SITE_URL,
            help=("Website for client auto-update")
        )
        common_parser.add_argument(
            "--beta-update-site-url",
            help=("Website for client beta auto-update")
        )
        common_parser.add_argument(
            "--debug", default=False, action="store_true",
            help="Fire a debugger (ipdb or pdb) one uncaught error."
        )
        common_parser.add_argument(
            "--nofscheck", default=False, action="store_true",
            help="Fire a debugger (ipdb or pdb) one uncaught error."
        )
        common_parser.add_argument(
            "--proxy-type",
            help="Choose a type of proxy"
        )
        common_parser.add_argument(
            "--proxy-server",
            help="Define proxy server"
        )
        common_parser.add_argument(
            "--proxy-exceptions",
            help="Add proxy exceptions ( separated by a comma )"
        )
        common_parser.add_argument(
            "--consider-ssl-errors", default=False, action="store_true",
            help="Don't ignore SSL errors in Qt network manager requests."
        )
        common_parser.add_argument(
            "--debug-pydev", default=False, action="store_true",
            help="Allow debugging with a PyDev server."
        )
        common_parser.add_argument(
            "--delay", default=self.default_remote_watcher_delay, type=int,
            help="Delay in seconds for remote polling.")
        common_parser.add_argument(
            "--max-sync-step", default=self.default_max_sync_step, type=int,
            help="Number of consecutive sync operations to perform"
            " without refreshing the internal state DB.")
        common_parser.add_argument(
            "--handshake-timeout", default=self.default_handshake_timeout,
            type=int,
            help="HTTP request timeout in seconds for the handshake.")
        common_parser.add_argument(
            "--timeout", default=self.default_timeout, type=int,
            help="HTTP request timeout in seconds for"
                " the sync Automation calls.")
        common_parser.add_argument(
            "--update-check-delay", default=DEFAULT_UPDATE_CHECK_DELAY,
            type=int,
            help="Delay in seconds between checks for application update.")
        common_parser.add_argument(
            # XXX: Make it true by default as the fault tolerant
            #  mode is not yet implemented
            "--stop-on-error", default=self.default_stop_on_error,
            action="store_true",
            help="Stop the process on first unexpected error."
            "Useful for developers and Continuous Integration.")
        common_parser.add_argument(
            "--max-errors", default=self.default_max_errors, type=int,
            help="Maximum number of tries before giving up synchronization of"
            " a file in error.")
        common_parser.add_argument(
            "-v", "--version", action="version", version=self.get_version(),
            help="Print the current version of the Nuxeo Drive client."
        )
        parser = argparse.ArgumentParser(
            parents=[common_parser],
            description="Command line interface for Nuxeo Drive operations.",
            usage=USAGE,
        )

        if not add_subparsers:
            return parser

        subparsers = parser.add_subparsers(
            title='Commands',
        )

        # Link to a remote Nuxeo server
        bind_server_parser = subparsers.add_parser(
            'bind-server', help='Attach a local folder to a Nuxeo server.',
            parents=[common_parser],
        )
        bind_server_parser.set_defaults(command='bind_server')
        bind_server_parser.add_argument(
            "--password", help="Password for the Nuxeo account")
        bind_server_parser.add_argument(
            "--local-folder",
            help="Local folder that will host the list of synchronized"
            " workspaces with a remote Nuxeo server.",
            default=DEFAULT_NX_DRIVE_FOLDER,
        )
        bind_server_parser.add_argument(
            "username", help="User account to connect to Nuxeo")
        bind_server_parser.add_argument("nuxeo_url",
                                        help="URL of the Nuxeo server.")
        bind_server_parser.add_argument(
            "--remote-repo", default=DEFAULT_REPOSITORY_NAME,
            help="Name of the remote repository.")

        # Unlink from a remote Nuxeo server
        unbind_server_parser = subparsers.add_parser(
            'unbind-server', help='Detach from a remote Nuxeo server.',
            parents=[common_parser],
        )
        unbind_server_parser.set_defaults(command='unbind_server')
        unbind_server_parser.add_argument(
            "--local-folder",
            help="Local folder that hosts the list of synchronized"
            " workspaces with a remote Nuxeo server.",
            default=DEFAULT_NX_DRIVE_FOLDER,
        )

        # Bind root folders
        bind_root_parser = subparsers.add_parser(
            'bind-root',
            help='Register a folder as a synchronization root.',
            parents=[common_parser],
        )
        bind_root_parser.set_defaults(command='bind_root')
        bind_root_parser.add_argument(
            "remote_root",
            help="Remote path or id reference of a folder to synchronize.")
        bind_root_parser.add_argument(
            "--local-folder",
            help="Local folder that will host the list of synchronized"
            " workspaces with a remote Nuxeo server. Must be bound with the"
            " 'bind-server' command.",
            default=DEFAULT_NX_DRIVE_FOLDER,
        )
        bind_root_parser.add_argument(
            "--remote-repo", default=DEFAULT_REPOSITORY_NAME,
            help="Name of the remote repository.")

        # Unlink from a remote Nuxeo root
        unbind_root_parser = subparsers.add_parser(
            'unbind-root', help='Unregister a folder as a synchronization root.',
            parents=[common_parser],
        )
        unbind_root_parser.set_defaults(command='unbind_root')
        unbind_root_parser.add_argument(
            "remote_root",
            help="Remote path or id reference of a folder to synchronize.")
        unbind_root_parser.add_argument(
            "--local-folder",
            help="Local folder that will host the list of synchronized"
            " workspaces with a remote Nuxeo server. Must be bound with the"
            " 'bind-server' command.",
            default=DEFAULT_NX_DRIVE_FOLDER,
        )
        unbind_root_parser.add_argument(
            "--remote-repo", default=DEFAULT_REPOSITORY_NAME,
            help="Name of the remote repository.")

        uninstall_parser = subparsers.add_parser(
            'uninstall', help='Remove app data',
            parents=[common_parser],
        )
        uninstall_parser.set_defaults(command='uninstall')

        console_parser = subparsers.add_parser(
            'console',
            help='Start in GUI-less mode.',
            parents=[common_parser],
        )
        console_parser.set_defaults(command='console')
        console_parser.add_argument(
            "--quit-if-done", default=False, action="store_true",
            help="Quit if synchronization is completed."
        )
        console_parser.add_argument(
            "--quit-timeout", default=DEFAULT_QUIT_TIMEOUT, type=int,
            help="Maximum uptime in seconds before quitting."
        )

        clean_parser = subparsers.add_parser(
            'clean_folder',
            help='Remove all ndrive attribute from this folder and childs.',
            parents=[common_parser],
        )
        clean_parser.add_argument(
            "--local-folder",
            help="Local folder to clean.",
        )
        clean_parser.set_defaults(command='clean_folder')

        # Display the metadata window
        metadata_parser = subparsers.add_parser(
            'metadata',
            help='Display the metadata window for a given file.',
            parents=[common_parser],
        )
        metadata_parser.set_defaults(command='metadata')
        metadata_parser.add_argument(
            "--file", default="",
            help="File path.")

        # embedded test runner base on nose:
        test_parser = subparsers.add_parser(
            'test',
            help='Run the Nuxeo Drive test suite.',
            parents=[common_parser],
        )
        test_parser.set_defaults(command='test')
        test_parser.add_argument(
            "-w", help="Nose working directory.")
        test_parser.add_argument(
            "--nologcapture", default=False, action="store_true",
            help="Disable nose logging capture plugin.")
        test_parser.add_argument(
            "--logging-format", help="Format of noestests log capture statements."
            " Uses the same format as used by standard logging handlers.")
        test_parser.add_argument(
            "--with-coverage", default=False, action="store_true",
            help="Compute coverage report.")
        test_parser.add_argument(
            "--with-profile", default=False, action="store_true",
            help="Compute profiling report.")

        return parser
    """Command Line Interface handler: parse options and execute operation"""

    def parse_cli(self, argv):
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
        protocol_url = None

        filtered_args = []
        for arg in argv[1:]:
            if arg.startswith('nxdrive://'):
                protocol_url = arg
                continue
            if not arg.startswith('-'):
                has_command = True
            filtered_args.append(arg)

        parser = self.make_cli_parser(add_subparsers=has_command)
        # Change default value according to config.ini
        self.load_config(parser)
        options = parser.parse_args(filtered_args)
        if options.debug:
            # Install Post-Mortem debugger hook

            def info(etype, value, tb):
                traceback.print_exception(etype, value, tb)
                print
                debugger.pm()

            sys.excepthook = info

        # Merge any protocol info into the other parsed commandline
        # parameters
        setattr(options, 'protocol_url', protocol_url)
        return options

    def load_config(self, parser):
        import ConfigParser
        config_name = 'config.ini'
        config = ConfigParser.ConfigParser()
        configs = []
        path = os.path.join(os.path.dirname(sys.executable), config_name)
        if os.path.exists(path):
            configs.append(path)
        if os.path.exists(config_name):
            configs.append(config_name)
        user_ini = os.path.expanduser(os.path.join(self.default_home, config_name))
        if os.path.exists(user_ini):
            configs.append(user_ini)
        if len(configs) > 0:
            config.read(configs)
        if config.has_option(ConfigParser.DEFAULTSECT, 'env'):
            env = config.get(ConfigParser.DEFAULTSECT, 'env')
            args = {}
            for item in config.items(env):
                if item[0] == 'env':
                    continue
                args[item[0].replace('-', '_')] = item[1]
            if len(args):
                parser.set_defaults(**args)

    def _configure_logger(self, options):
        """Configure the logging framework from the provided options"""
        filename = options.log_filename
        if filename is None:
            filename = os.path.join(
                options.nxdrive_home, 'logs', 'nxdrive.log')

        configure(
            use_file_handler=True,
            log_filename=filename,
            file_level=options.log_level_file,
            console_level=options.log_level_console,
            command_name=options.command,
        )

    def uninstall(self, options):
        try:
            self.manager.get_osi().uninstall()
            # Remove all token first
            self.manager.unbind_all()
            self.manager.dispose_db()
            import shutil
            shutil.rmtree(self.manager.nxdrive_home)
        except Exception, e:
            # Exit with 0 signal to not block the uninstall
            print e
            sys.exit(0)

    def handle(self, argv):
        """Parse options, setup logs and manager and dispatch execution."""
        options = self.parse_cli(argv)
        if hasattr(options, 'local_folder'):
            options.local_folder = normalized_path(options.local_folder)
        # 'launch' is the default command if None is provided
        command = options.command = getattr(options, 'command', 'launch')

        if command != 'test' and command != 'uninstall':
            # Configure the logging framework, except for the tests as they
            # configure their own.
            # Don't need uninstall logs either for now.
            self._configure_logger(options)

        self.log = get_logger(__name__)
        self.log.debug("Command line: argv=%r, options=%r",
                       ' '.join(argv), options)

        if command != 'test' and command != 'uninstall':
            # Install utility to help debugging segmentation faults
            self._install_faulthandler(options)

        if command != 'test':
            # Initialize a manager for this process, except for the tests
            # as they initialize their own
            self.manager = self.get_manager(options)

        # Find the command to execute based on the
        handler = getattr(self, command, None)
        if handler is None:
            raise NotImplementedError(
                'No handler implemented for command ' + options.command)

        try:
            return handler(options)
        except Exception, e:
            if command == 'test' or options.debug:
                # Make it possible to use the postmortem debugger
                raise
            else:
                msg = e.msg if hasattr(e, 'msg') else e
                self.log.error("Error executing '%s': %s", command, msg,
                          exc_info=True)

    def get_manager(self, options):
        from nxdrive.manager import Manager
        return Manager(options)

    def _get_application(self, options, console=False):
        if console:
            from nxdrive.console import ConsoleApplication
            return ConsoleApplication(self.manager, options)
        else:
            from nxdrive.wui.application import Application
            return Application(self.manager, options)

    def launch(self, options=None, console=False):
        """Launch the Qt app in the main thread and sync in another thread."""
        from nxdrive.utils import PidLockFile
        lock = PidLockFile(self.manager.get_configuration_folder(), "qt")
        if lock.lock() is not None:
            self.log.warning("Qt application already running: exiting")
            # Handle URL if needed
            self.manager.get_drive_edit().handle_url()
            return
        app = self._get_application(options, console=console)
        exit_code = app.exec_()
        lock.unlock()
        self.log.debug("Qt application exited with code %r", exit_code)
        return exit_code

    def clean_folder(self, options):
        from nxdrive.client.local_client import LocalClient
        if options.local_folder is None:
            print "A folder must be specified"
            return 0
        client = LocalClient(unicode(options.local_folder))
        client.clean_xattr_root()
        return 0

    def console(self, options):
        if options.debug_pydev:
            from pydev import pydevd
            pydevd.settrace()
        return self.launch(options=options, console=True)

    def metadata(self, options):
        from nxdrive.wui.metadata import MetadataApplication
        self.log.debug('Opening metadata window for %r', options.file)
        app = MetadataApplication(self.manager, options)
        return app.exec_()

    def edit(self, options):
        # Kept for backward compatibility
        self.launch(options)
        return 0

    def download_edit(self, options):
        self.launch(options)
        return 0

    def bind_server(self, options):
        check_credentials = True
        if options.password is None:
            password = getpass()
        else:
            password = options.password
            if password == "":
                password = None
                check_credentials = False
        if options.local_folder is None or options.local_folder == "":
            options.local_folder = DEFAULT_NX_DRIVE_FOLDER
        self.manager.bind_server(options.local_folder, options.nuxeo_url,
                                    options.username, password, start_engine=False,
                                    check_credentials=check_credentials)
        return 0

    def unbind_server(self, options):
        for uid, engine in self.manager.get_engines().iteritems():
            if engine.get_local_folder() == options.local_folder:
                self.manager.unbind_engine(uid)
                return 0
        return 0

    def bind_root(self, options):
        for engine in self.manager.get_engines().values():
            self.log.trace("Comparing: %s to %s", engine.get_local_folder(), options.local_folder)
            if engine.get_local_folder() == options.local_folder:
                engine.get_remote_doc_client(repository=options.remote_repo).register_as_root(options.remote_root)
                return 0
        self.log.error('No engine registered for local folder %s', options.local_folder)
        return 1

    def unbind_root(self, options):
        for engine in self.manager.get_engines().values():
            if engine.get_local_folder() == options.local_folder:
                engine.get_remote_doc_client(repository=options.remote_repo).unregister_as_root(options.remote_root)
                return 0
        self.log.error('No engine registered for local folder %s', options.local_folder)
        return 1

    def test(self, options):
        import nose
        # Monkeypatch nose usage message as it's complicated to include
        # the missing text resource in the frozen binary package
        nose.core.TestProgram.usage = lambda cls: ""
        argv = [
            '',
            '--verbose',
            '--stop',
        ]

        if options.w:
            argv += [
                '-w',
                options.w,
            ]

        if options.nologcapture:
            argv += [
                '--nologcapture',
            ]

        if options.logging_format:
            argv += [
                '--logging-format',
                options.logging_format,
            ]

        if options.with_coverage:
            argv += [
                '--with-coverage',
                '--cover-package=nxdrive',
                '--cover-html',
                '--cover-html-dir=coverage',
            ]

        if options.with_profile:
            argv += [
                '--with-profile',
                '--profile-restrict=nxdrive',
            ]
        if "TESTS" not in os.environ or os.environ["TESTS"].strip() == "":
            # List the test modules explicitly as recursive discovery is broken
            # when the app is frozen.
            argv += [
                "nxdrive.tests.test_bind_server",
                "nxdrive.tests.test_blacklist_queue",
                "nxdrive.tests.test_commandline",
                "nxdrive.tests.test_conflicts",
                "nxdrive.tests.test_copy",
                "nxdrive.tests.test_drive_edit",
                "nxdrive.tests.test_encoding",
                "nxdrive.tests.test_engine_dao",
                "nxdrive.tests.test_integration_concurrent_synchronization",
                "nxdrive.tests.test_integration_local_root_deletion",
                "nxdrive.tests.test_local_client",
                "nxdrive.tests.test_local_copy_paste",
                "nxdrive.tests.test_local_create_folders",
                "nxdrive.tests.test_local_deletion",
                "nxdrive.tests.test_local_filter",
                "nxdrive.tests.test_local_move_and_rename",
                "nxdrive.tests.test_local_move_folders",
                "nxdrive.tests.test_local_paste",
                "nxdrive.tests.test_local_storage_space_issue",
                "nxdrive.tests.test_manager_dao",
                "nxdrive.tests.test_model_filters",
                "nxdrive.tests.test_multiple_files",
                "nxdrive.tests.test_permission_hierarchy",
                "nxdrive.tests.test_readonly",
                "nxdrive.tests.test_reinit_database",
                "nxdrive.tests.test_remote_changes",
                "nxdrive.tests.test_remote_deletion",
                "nxdrive.tests.test_remote_document_client",
                "nxdrive.tests.test_remote_file_system_client",
                "nxdrive.tests.test_remote_move_and_rename",
                "nxdrive.tests.test_report",
                "nxdrive.tests.test_security_updates",
                "nxdrive.tests.test_shared_folders",
                "nxdrive.tests.test_sync_roots",
                "nxdrive.tests.test_synchronization",
                "nxdrive.tests.test_synchronization_dedup",
                "nxdrive.tests.test_synchronization_dedup_case_sensitive",
                "nxdrive.tests.test_translator",
                "nxdrive.tests.test_updater",
                "nxdrive.tests.test_utils",
                "nxdrive.tests.test_versioning",
                # "nxdrive.tests.test_volume",
                "nxdrive.tests.test_watchers",
                "nxdrive.tests.test_windows",
            ]
        else:
            argv.extend(['nxdrive.tests.' + test for test in os.environ["TESTS"].strip().split(",")])
        return 0 if nose.run(argv=argv) else 1

    def _install_faulthandler(self, options):
        """Utility to help debug segfaults"""
        try:
            # Use faulthandler to print python tracebacks in case of segfaults
            import faulthandler
            segfault_filename = os.path.join(
                options.nxdrive_home, 'logs', 'segfault.log')
            segfault_file = open(os.path.expanduser(segfault_filename), 'w')
            self.log.debug("Enabling faulthandler to trace segfaults in %s",
                           segfault_filename)
            faulthandler.enable(file=segfault_file)
        except ImportError:
            self.log.debug("faulthandler is not available: skipped")


def dumpstacks(signal, frame):
    id2name = dict([(th.ident, th.name) for th in threading.enumerate()])
    code = []
    for thread_id, stack in sys._current_frames().items():
        code.append("\n# Thread: %s(%d)" % (id2name.get(thread_id, ""),
                                            thread_id))
        for filename, lineno, name, line in traceback.extract_stack(stack):
            code.append('File: "%s", line %d, in %s'
                        % (filename, lineno, name))
            if line:
                code.append("  %s" % (line.strip()))
    print "\n".join(code)


def win32_unicode_argv():
    """Uses shell32.GetCommandLineArgvW to get sys.argv as a list of Unicode
    strings.

    Versions 2.x of Python don't support Unicode in sys.argv on
    Windows, with the underlying Windows API instead replacing multi-byte
    characters with '?'.

    See http://stackoverflow.com/questions/846850/read-unicode-characters-from-command-line-arguments-in-python-2-x-on-windows
    """

    from ctypes import POINTER, byref, cdll, c_int, windll
    from ctypes.wintypes import LPCWSTR, LPWSTR

    GetCommandLineW = cdll.kernel32.GetCommandLineW
    GetCommandLineW.argtypes = []
    GetCommandLineW.restype = LPCWSTR

    CommandLineToArgvW = windll.shell32.CommandLineToArgvW
    CommandLineToArgvW.argtypes = [LPCWSTR, POINTER(c_int)]
    CommandLineToArgvW.restype = POINTER(LPWSTR)

    cmd = GetCommandLineW()
    argc = c_int(0)
    argv = CommandLineToArgvW(cmd, byref(argc))
    if argc.value > 0:
        # Remove Python executable and commands if present
        start = argc.value - len(sys.argv)
        return [argv[i] for i in
                xrange(start, argc.value)]


def main(argv=None):
    # Print thread dump when receiving SIGUSR1,
    # except under Windows (no SIGUSR1)
    import signal
    # Get the Ctrl+C to interrupt application
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    if sys.platform != 'win32':
        signal.signal(signal.SIGUSR1, dumpstacks)
    if argv is None:
        argv = win32_unicode_argv() if sys.platform == 'win32' else sys.argv
    return CliHandler().handle(argv)

if __name__ == "__main__":
    sys.exit(main())
