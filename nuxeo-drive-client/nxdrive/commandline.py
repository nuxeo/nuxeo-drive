"""Utilities to operate Nuxeo Drive from the command line"""
import sys
import argparse
from getpass import getpass


from nxdrive.controller import Controller


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
    attach_parser = subparsers.add_parser(
        'attach', help='Detach a local folder to a Nuxeo server.')
    attach_parser.set_defaults(command='attach')
    attach_parser.add_argument(
        "--password", help="Password for the Nuxeo account")
    attach_parser.add_argument(
        "--local-folder",
        help="Local folder that will host the list of synchronized"
        " workspaces with a remote Nuxeo server.",
        default="~/Nuxeo Drive",
    )
    attach_parser.add_argument(
        "username", help="User account to connect to Nuxeo")
    attach_parser.add_argument("nuxeo_url", help="URL of the Nuxeo server.")

    # Unlink from a remote Nuxeo server
    detach_parser = subparsers.add_parser(
        'detach', help='Detach from a remote Nuxeo server.')
    detach_parser.set_defaults(command='detach')
    detach_parser.add_argument("nuxeo_url", help="URL of the Nuxeo server.")

    # Start / Stop the synchronization daemon
    start_parser = subparsers.add_parser(
        'start', help='Start the synchronization daemon')
    start_parser.set_defaults(command='start')
    stop_parser = subparsers.add_parser(
        'stop', help='Stop the synchronization daemon')
    stop_parser.set_defaults(command='stop')

    # Introspect current synchronization status
    status_parser = subparsers.add_parser(
        'status',
        help='Query the synchronization status of files and folders.'
    )
    status_parser.set_defaults(command='status')
    status_parser.add_argument(
        "files", nargs="*", help='Files to query status on')

    return parser


class CliHandler(object):
    """Command Line Interface handler: parse options and execute operation"""

    def __init__(self):
        self.parser = make_cli_parser()

    def handle(self, args):
        # use the CLI parser to check that the first args is a valid command
        options = self.parser.parse_args(args)
        self.controller = Controller(options.nxdrive_home, process_type='cli')

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

    def status(self, options):
        states = self.controller.status(options.files)
        for filename, status in states:
            print status + '\t' + filename
        return 0

    def attach(self, options):
        if options.password is None:
            password = getpass()
        else:
            password = options.password
        self.controller.attach(options.local_folder, options.nuxeo_url,
                               options.username, password)
        return 0


def main(args=None):
    if args is None:
        args = sys.argv[1:]
    return CliHandler().handle(args)
