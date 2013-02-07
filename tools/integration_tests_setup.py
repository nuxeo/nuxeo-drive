r"""Setup the windows machine for Continuous Integration on the MSI package

Steps executed by this script:

    - unzip the Nuxeo distribution
    - deploy the marketplace package of nuxeo-drive
    - start the server
    - setup test environment variables

Under Windows:

    - download http://code.google.com/p/lessmsi if not already there
    - extract the MSI archive in a local, non system folder with lessmsi
    - launch the ``ndrive test`` command to run the integration tests

Under POSIX:

    - build the nuxeo-drive-client from the source using system python
    - run the integration tests with nosetests

Both:

    - stop the server and collect the logs

Get the help on running this with::

    python integration_tests_setup.py --help

"""

import os
import sys
import urllib2
import argparse
import re
import zipfile
import shutil
import atexit
import time
import fnmatch


DEFAULT_MARKETPLACE = os.path.join(
    "packaging", "nuxeo-drive-marketplace", "target")
DEFAULT_ARCHIVE_PREFIX = "nuxeo-distribution-tomcat-"
NUXEO_FOLDER='nuxeo-tomcat'
MARKET_PLACE_PREFIX = "nuxeo-drive-marketplace"

DEFAULT_MSI_FOLDER = os.path.join(r"dist")
DEFAULT_LESSMSI_URL="http://lessmsi.googlecode.com/files/lessmsi-v1.0.8.zip"
LESSMSI_FOLDER='lessmsi'
EXTRACTED_MSI_FOLDER='nxdrive_msi'

LINKS_PATTERN = r'\bhref="([^"]+)"'

MSI_PATTERN = r"nuxeo-drive-\d\.\d\..*?\.msi"
DMG_PATTERN = r"Nuxeo%20Drive\.dmg"

WAR_FOLDER = os.path.join(
    "nuxeo-drive-server", "nuxeo-drive-jsf", "src", "main",
    "resources", "web", "nuxeo.war", "nuxeo-drive")


def pflush(message):
    """This is required to have messages in the right order in jenkins"""
    print message
    sys.stdout.flush()


def execute(cmd, exit_on_failure=True):
    pflush("> " + cmd)
    code = os.system(cmd)
    if code != 0 and exit_on_failure:
        pflush("Command %s returned with code %d" % (cmd, code))
        sys.exit(code)


def parse_args(args=None):
    parser = argparse.ArgumentParser(
        description="Integration tests coordinator")
    subparsers = parser.add_subparsers(title="Commands")

    # Fetch packaging dependencies from other Jenkins jobs
    fetch_parser = subparsers.add_parser(
        'fetch', help="Fetch packages from Jenkins pages")
    fetch_parser.set_defaults(command='fetch')

    fetch_parser.add_argument('--msi-url')
    fetch_parser.add_argument('--dmg-url')

    # Integration test launcher
    test_parser = subparsers.add_parser(
        'test', help="Launch the integration tests")
    test_parser.set_defaults(command='test')

    test_parser.add_argument("--msi-folder", default=DEFAULT_MSI_FOLDER)
    test_parser.add_argument("--lessmsi-url", default=DEFAULT_LESSMSI_URL)

    return parser.parse_args(args)


def download(url, filename):
    if not os.path.exists(filename):
        pflush("Downloading %s to %s" % (url, filename))
        headers = {'User-Agent' : 'nxdrive test script'}
        req = urllib2.Request(url, None, headers)
        reader = urllib2.urlopen(req)
        with open(filename, 'wb') as f:
            while True:
                b = reader.read(1000 ** 2)
                if b == '':
                    break
                f.write(b)


def unzip(filename, target=None):
    pflush("Unzipping " + filename)
    zf = zipfile.ZipFile(filename, 'r')
    for info in zf.infolist():
        filename = info.filename
        # Skip first directory entry
        if filename.endswith('/'):
            continue
        if target is not None:
            filename = os.path.join(target, filename)
        dirname = os.path.dirname(filename)
        if dirname != '' and not os.path.exists(dirname):
            os.makedirs(dirname)
        with open(filename, 'wb') as f:
            f.write(zf.read(info.filename))


def find_latest(folder, prefix=None, suffix=None):
    files = os.listdir(folder)
    if prefix is not None:
        files = [f for f in files if f.startswith(prefix)]
    if suffix is not None:
        files = [f for f in files if f.endswith(suffix)]
    if not files:
        raise RuntimeError(('Could not find file with prefix "%s"'
                            'and suffix "%s" in "%s"')
                           % (prefix, suffix, folder))
    files.sort()
    return os.path.join(folder, files[-1])


def find_package_url(archive_page_url, pattern):
    pflush("Finding latest package at: " + archive_page_url)
    index_html = urllib2.urlopen(archive_page_url).read()
    candidates = []
    archive_pattern = re.compile(pattern)
    for link in re.compile(LINKS_PATTERN).finditer(index_html):
        link_url = link.group(1)
        if "/" in link_url:
            link_filename = link_url.rsplit("/", 1)[1]
        else:
            link_filename = link_url
        if archive_pattern.match(link_filename):
            candidates.append(link_url)

    if not candidates:
        raise ValueError("Could not find packages with pattern %r on %s"
                         % (pattern, archive_page_url))
    candidates.sort()
    archive = candidates[0]
    if archive.startswith("http"):
        archive_url = archive
    else:
        if not archive_page_url.endswith('/'):
            archive_page_url += '/'
        archive_url = archive_page_url + archive
    return archive_url, archive_url.rsplit('/', 1)[1]


def setup_nuxeo():
    try:
        java_home = os.environ['JAVA_HOME']
    except KeyError:
        raise RuntimeError('The JAVA_HOME env variable is required.')
    if sys.platform == 'win32':
        java_bin = os.path.join(java_home, 'bin')
        path = os.environ['PATH']
        if not java_bin in path:
            os.environ['PATH'] = path + ";" + java_bin

        pflush("Kill previous soffice if any to unlock old files")
        execute('taskkill /f /fi "imagename eq soffice.*"',
                exit_on_failure=False)

        pflush("Kill any potential rogue instance of ndrive.exe")
        execute('taskkill /f /fi "imagename eq ndrive.exe"',
                exit_on_failure=False)

        pflush("Waiting for any killed process to actually stop")
        time.sleep(1.0)

    filepath = find_latest(DEFAULT_MARKETPLACE, prefix=DEFAULT_ARCHIVE_PREFIX,
                          suffix=".zip")
    unzip(filepath, target='unzip.tmp')
    nuxeo_folder_name = os.listdir('unzip.tmp')[0]
    nuxeo_folder_path = os.path.join('unzip.tmp', nuxeo_folder_name)

    nuxeoctl = os.path.join(NUXEO_FOLDER, 'bin', 'nuxeoctl')
    if os.path.exists(NUXEO_FOLDER):
        pflush("Stopping previous instance of Nuxeo")
        # stop any previous server process that could have been left running
        # if jenkins kills this script
        if sys.platform != 'win32':
            execute("chmod +x " + nuxeoctl, exit_on_failure=False)
        execute(nuxeoctl + " --gui false stop", exit_on_failure=False)
        pflush("Deleting folder: " + NUXEO_FOLDER)
        if sys.platform == 'win32':
            # work around for long filenames under windows
            execute('rmdir /s /q ' + NUXEO_FOLDER)
            deleted = False
            for i in range(3):
                if not os.path.exists(NUXEO_FOLDER):
                    deleted = True
                    break
                else:
                    pflush('Waiting for windows to finish deleting files')
                    time.sleep(1.0)
            if not deleted:
                raise RuntimeError("Failed to delete " + NUXEO_FOLDER)
        else:
            shutil.rmtree(NUXEO_FOLDER)

    pflush("Renaming %s to %s" % (nuxeo_folder_path, NUXEO_FOLDER))
    os.rename(nuxeo_folder_path, NUXEO_FOLDER)
    with open(os.path.join(NUXEO_FOLDER, 'bin', 'nuxeo.conf'), 'ab') as f:
        f.write("\nnuxeo.wizard.done=true\n")

    if sys.platform != 'win32':
        execute("chmod +x " + nuxeoctl)

    pflush("Installing the nuxeo drive marketplace package")
    package = find_latest(DEFAULT_MARKETPLACE, prefix=MARKET_PLACE_PREFIX,
                          suffix=".zip")
    execute(nuxeoctl + " mp-install --accept=true --nodeps " + package)

    pflush("Starting the Nuxeo server")
    execute(nuxeoctl + " --gui false start")

    # Register a callback to stop the nuxeo server
    atexit.register(execute, nuxeoctl + " --gui false stop")


def extract_msi(lessmsi_url, msi_folder):
    if os.path.isdir(msi_folder):
        msi_filename = find_latest(msi_folder, suffix='.msi')
    else:
        msi_filename = msi_folder

    if not os.path.exists(LESSMSI_FOLDER):
        filename = os.path.basename(lessmsi_url)
        download(lessmsi_url, filename)
        unzip(filename, target=LESSMSI_FOLDER)

    pflush("Extracting the MSI")
    lessmsi = os.path.join(LESSMSI_FOLDER, 'lessmsi')
    if os.path.exists(EXTRACTED_MSI_FOLDER):
        shutil.rmtree(EXTRACTED_MSI_FOLDER)
    execute("%s /x %s %s" % (lessmsi, msi_filename, EXTRACTED_MSI_FOLDER))


def set_environment():
    os.environ['NXDRIVE_TEST_NUXEO_URL'] = "http://localhost:8080/nuxeo"
    os.environ['NXDRIVE_TEST_USER'] = "Administrator"
    os.environ['NXDRIVE_TEST_PASSWORD'] = "Administrator"

def clean_pyc():
    for root, dirnames, filenames in os.walk('nuxeo-drive-client'):
        if '.git' in dirnames:
            dirnames.remove('.git')
        for filename in fnmatch.filter(filenames, '*.pyc'):
            file_path = os.path.join(root, filename)
            print('Removing .pyc file: %s' % file_path)
            os.unlink(file_path)

def run_tests_from_msi():
    ndrive = os.path.join(EXTRACTED_MSI_FOLDER, 'SourceDir', 'ndrive.exe')
    execute(ndrive + " test")


def run_tests_from_source():
    execute("cd nuxeo-drive-client && nosetests")


def download_package(url, pattern, target_folder):
    url, filename = find_package_url(url, pattern)
    filepath = os.path.join(target_folder, urllib2.unquote(filename))
    download(url, filepath)


if __name__ == "__main__":
    options = parse_args()

    if options.command == 'test':
        setup_nuxeo()
        set_environment()
        clean_pyc()
        if sys.platform == 'win32':
            extract_msi(options.lessmsi_url, options.msi_folder)
            run_tests_from_msi()
        else:
            run_tests_from_source()
    elif options.command == 'fetch':
        if os.path.exists(WAR_FOLDER):
            shutil.rmtree(WAR_FOLDER)
        os.makedirs(WAR_FOLDER)
        if options.msi_url is not None:
            download_package(options.msi_url, MSI_PATTERN, WAR_FOLDER)
        if options.dmg_url is not None:
            download_package(options.dmg_url, DMG_PATTERN, WAR_FOLDER)
