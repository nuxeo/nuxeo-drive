"""Utilities to operate Nuxeo Drive from the command line"""
import sys
import argparse
from getpass import getpass


from nxdrive.controller import Controller

DEFAULT_NX_DRIVE_FOLDER = '~/Nuxeo Drive'


def make_cli_parser():
    """Parse commandline arguments using a git-like subcommands scheme"""

    parser = argparse.ArgumentParser(
        description="Command line interface for Nuxeo Drive operations.")

    parser.add_argument(
        "--nxdrive-home",
        default="~/.nuxeo-drive",
        help="Folder to store the Nuxeo Drive configuration."
    )

    subparsers = parser.add_subparsers(
        title='Commands:',
    )

    # Link to a remote Nuxeo server
    bind_server_parser = subparsers.add_parser(
        'bind-server', help='Attach a local folder to a Nuxeo server.')
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

    # Unlink from a remote Nuxeo server
    unbind_server_parser = subparsers.add_parser(
        'unbind-server', help='Detach from a remote Nuxeo server.')
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
        help='Attach a local folder as a root for synchronization.')
    bind_root_parser.set_defaults(command='bind_root')
    bind_root_parser.add_argument(
        "remote_root",
        help="Remote path or id reference of a folder to sychronize.")
    bind_root_parser.add_argument(
        "--local-folder",
        help="Local folder that will host the list of synchronized"
        " workspaces with a remote Nuxeo server. Must be bound with the"
        " 'bind-server' command.",
        default=DEFAULT_NX_DRIVE_FOLDER,
    )
    bind_root_parser.add_argument(
        "--remote-repo", default='default',
        help="Name of the remote repository.")

    # Unlink from a remote Nuxeo root
    unbind_root_parser = subparsers.add_parser(
        'unbind-root', help='Detach from a remote Nuxeo root.')
    unbind_root_parser.set_defaults(command='unbind_root')
    unbind_root_parser.add_argument(
        "local_root", help="Local sub-folder to de-synchronize.")

    # Start / Stop the synchronization daemon
    start_parser = subparsers.add_parser(
        'start', help='Start the synchronization daemon')
    start_parser.set_defaults(command='start')
    stop_parser = subparsers.add_parser(
        'stop', help='Stop the synchronization daemon')
    stop_parser.set_defaults(command='stop')
    console_parser = subparsers.add_parser(
        'console',
        help='Start the synchronization without detaching the process.')
    console_parser.set_defaults(command='console')
    console_parser.add_argument(
        "--delay", default=5.0, type=float,
        help="Delay in seconds between consecutive sync operations.")
    console_parser.add_argument(
        "--stop-on-error", default=True, action="store_false",
        help="Stop the process on first unexpected error."
        "Useful for developers and Continuous Integration.")

# TODO:rewrite me
#    # Introspect current synchronization status
#    status_parser = subparsers.add_parser(
#        'status',
#        help='Query the synchronization status of files and folders.'
#    )
#    status_parser.set_defaults(command='status')
#    status_parser.add_argument(
#        "files", nargs="*", help='Files to query status on')

    return parser


class CliHandler(object):
    """Command Line Interface handler: parse options and execute operation"""

    def __init__(self):
        self.parser = make_cli_parser()

    def handle(self, args):
        # use the CLI parser to check that the first args is a valid command
        options = self.parser.parse_args(args)
        self.controller = Controller(options.nxdrive_home)

        handler = getattr(self, options.command, None)
        if handler is None:
            raise NotImplementedError(
                'No handler implemented for command ' + options.command)
        return handler(options)

    def start(self, options=None):
        self.controller.start()
        return 0

    def stop(self, options=None):
        self.controller.stop()
        return 0

    def console(self, options):
        fault_tolerant = not options.stop_on_error
        try:
            self.controller.loop(fault_tolerant=fault_tolerant,
                                 delay=options.delay)
        except KeyboardInterrupt:
            self.controller.get_session().rollback()
        return 0

    def status(self, options):
        states = self.controller.status(options.files)
        for filename, status in states:
            print status + '\t' + filename
        return 0

    def bind_server(self, options):
        if options.password is None:
            password = getpass()
        else:
            password = options.password
        self.controller.bind_server(options.local_folder, options.nuxeo_url,
                                    options.username, password)
        return 0

    def unbind_server(self, options):
        self.controller.unbind_server(options.local_folder)
        return 0

    def bind_root(self, options):
        self.controller.bind_root(options.local_folder, options.remote_root,
                                  repository=options.remote_root)
        return 0

    def unbind_root(self, options):
        self.controller.unbind_root(options.local_root)
        return 0


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    return CliHandler().handle(args)

if __name__ == "__main__":
    main()
