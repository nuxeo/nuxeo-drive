# coding: utf-8
"""
NXDRIVE-961: We need to be strong against any update process regressions.

That script will:

1. generate an executable for a given version lesser than the current one,
   let's say 1.2.2 if the current version is 1.2.3
2. start un local webserver containing all required files for a complete upgrade
3. starts the executable using the local webserver as beta update canal
4. start Drive and let the auto-upgrade working
check that the Drive version is 1.2.3

It __must__ be launched before any new release to validate the update process.
"""

from __future__ import print_function, unicode_literals

import SimpleHTTPServer
import SocketServer
import distutils.dir_util
import distutils.version
import glob
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

__version__ = '0.1.2'


class Server(SimpleHTTPServer.SimpleHTTPRequestHandler):
    """ Simple server handler to emulate custom responses. """

    def do_GET(self):
        if self.path.endswith('.json'):
            if re.match(r'^/\d\.\d\.\d\.json$', self.path):
                # Serve files like "2.5.5.json"
                content = b'{"nuxeoPlatformMinVersion": "5.6"}'
            else:
                # Serve files like "9.2.json" or 9.3-SNAPSHOT.json"
                content = b'{"nuxeoDriveMinVersion": "2.0.1028"}'
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Content-length', 4 * len(content))
            self.end_headers()
            path = self.path.lstrip('/')
            open(path, 'wb').write(content)
            f = open(path, 'rb')
        else:
            f = self.send_head()
        if f:
            try:
                self.copyfile(f, self.wfile)
            finally:
                f.close()


def gen_exe():
    """ Generate an executable. """

    if sys.platform == 'linux2':
        cmd = 'sh tools/linux/deploy_jenkins_slave.sh --build'
    elif sys.platform == 'darwin':
        cmd = 'sh tools/osx/deploy_jenkins_slave.sh --build'
    else:
        cmd = ('powershell -ExecutionPolicy Unrestricted'
               ' . ".\\tools\\windows\\deploy_jenkins_slave.ps1" -build')

    print('>>> Command:', cmd)
    output = subprocess.check_output(cmd.split())
    return output.decode('utf-8').strip()


def launch_drive(archive):
    """ Launch Drive and wait for auto-update. """

    # Be patient, especially on Windows ...
    time.sleep(5)

    # Extract the fresh Drive archive
    with zipfile.ZipFile(archive) as handler:
        handler.extractall()

    # Again, be patient, especially on macOS ...
    time.sleep(5)

    if sys.platform == 'linux2':
        cmd = './ndrive'
    elif sys.platform == 'darwin':
        # Adjust rights
        subprocess.check_output(['chmod', '-R', '+x', 'Nuxeo Drive.app'])
        cmd = './Nuxeo Drive.app/Contents/MacOS/ndrive'
    else:
        cmd = 'ndrive.exe'

    args = [
        cmd,
        '--log-level-console=TRACE',
        # '--update-check-delay=3',
        '--update-site-url=http://localhost:8000',
        '--beta-update-site-url=http://localhost:8000',
    ]
    output = subprocess.check_output(args)
    return output.decode('utf-8').strip()


def webserver(folder, port=8000):
    """ Start a local web server. """

    os.chdir(folder)
    httpd = SocketServer.TCPServer(('', port), Server)
    print('>>> Serving', folder, 'at http://localhost:8000')
    print('>>> CTRL+C to terminate')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


def version_decrement(version):
    """ Guess the lower version of the one given. """

    major, minor, patch = map(int, version.split('.'))

    patch -= 1
    if patch < 0:
        patch = 9
        minor -= 1
    if minor < 0:
        minor = 9
        major -= 1

    return '.'.join(map(str, [major, minor, patch]))


def version_find():
    """
    Find the current Drive version.

    :return tuple: The version and line number where it is defined.
    """

    path = os.path.join('nuxeo-drive-client', 'nxdrive', '__init__.py')
    with io.open(path, encoding='utf-8') as handler:
        for lineno, line in enumerate(handler.readlines()):
            if line.startswith('__version__'):
                return re.findall(r"'(.+)'", line)[0], lineno


def version_update(version, lineno):
    """ Update Drive version. """

    path = os.path.join('nuxeo-drive-client', 'nxdrive', '__init__.py')

    with io.open(path, encoding='utf-8') as handler:
        content = handler.readlines()

    content[lineno] = "__version__ = '{}'".format(version)

    with io.open(path, 'w', encoding='utf-8', newline='\n') as handler:
        handler.write(''.join(content) + '\n')


def tests():
    """ Simple tests before doing anything. """

    version_checker = distutils.version.StrictVersion
    assert version_decrement('1.0.0') == '0.9.9'
    assert version_decrement('2.5.0') == '2.4.9'
    assert version_decrement('1.2.3') == '1.2.2'
    assert version_decrement('1.2.333') == '1.2.332'
    assert version_checker(version_decrement('1.0.0'))
    assert version_checker(version_decrement('2.5.0'))
    assert version_checker(version_decrement('1.2.3'))
    assert version_checker(version_decrement('1.2.333'))
    return 1


def main():
    """ Main logic. """

    # Cleanup
    try:
        shutil.rmtree('dist')
    except OSError:
        pass

    version_checker = distutils.version.StrictVersion
    src = os.getcwd()
    dst = tempfile.mkdtemp()

    # Generate the current version executable
    version, lineno = version_find()
    print('>>> Current version is', version, 'at line', lineno)
    assert version_checker(version)
    gen_exe()

    # Move files to the webserver
    for file_ in glob.glob('dist/*{}*'.format(version)):
        if os.path.isdir(file_):
            continue
        dst_file = os.path.join(dst, os.path.basename(file_))
        print('>>> Moving', file_, '->', dst)
        os.rename(file_, dst_file)

    # Guess the anterior version
    previous = version_decrement(version)
    print('>>> Testing upgrade', previous, '->', version)
    assert version_checker(previous)

    try:
        # Update the version in Drive code source to emulate an old version
        version_update(previous, lineno)
        assert version_find() == (previous, lineno)

        # Generate the executable
        gen_exe()

        # Move the file to test to the webserver
        src_file = glob.glob('dist/*{}*.zip'.format(previous))[0]
        archive = os.path.basename(src_file)
        dst_file = os.path.join(dst, archive)
        print('>>> Moving', src_file, '->', dst)
        os.rename(src_file, dst_file)

        # Launch Drive in its own thread
        os.chdir(dst)
        threading.Thread(target=launch_drive, args=(archive,)).start()

        # Start the web server
        webserver(dst)
    finally:
        os.chdir(src)

        # Restore the original version
        version_update(version, lineno)

        # Cleanup
        try:
            shutil.rmtree(dst)
        except OSError:
            pass


if __name__ == '__main__':
    exit(tests() and main())
