# coding: utf-8
import signal
import sys


from nxdrive.commandline import CliHandler


def dumpstacks(*args, **kwargs):
    import threading
    import traceback

    id2name = dict([(th.ident, th.name) for th in threading.enumerate()])
    code = []
    for thread_id, stack in sys._current_frames().items():
        code.append(
            '\n# Thread: %s(%d)' % (id2name.get(thread_id, ''), thread_id))
        for filename, lineno, name, line in traceback.extract_stack(stack):
            code.append(
                'File: "%s", line %d, in %s' % (filename, lineno, name))
            if line:
                code.append('  %s' % (line.strip()))
    print('\n'.join(code))


def win32_unicode_argv():
    """ Uses shell32.GetCommandLineArgvW to get sys.argv as a list of Unicode
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
        return [argv[i] for i in range(start, argc.value)]


def main():
    if sys.version_info[0] != 2 or sys.version_info[1] != 7:
        raise RuntimeError('Nuxeo Drive requires Python 2.7')

    # Print thread dump when receiving SIGUSR1,
    # except under Windows (no SIGUSR1)
    # Get the Ctrl+C to interrupt application
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    if sys.platform != 'win32':
        signal.signal(signal.SIGUSR1, dumpstacks)

    argv = win32_unicode_argv() if sys.platform == 'win32' else sys.argv
    return CliHandler().handle(argv)


sys.exit(main())
