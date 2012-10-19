r"""Setup the windows machine for Continuous Integration on the MSI package

Steps executed by this script:

    - download the latest nightly build of Nuxeo from Jenkins
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


DEFAULT_MARKETPLACE = os.path.join(
    "packaging", "nuxeo-drive-marketplace", "target")
MARKET_PLACE_PREFIX = "nuxeo-drive-marketplace"
DEFAULT_MSI = os.path.join(r"dist")
DEFAULT_NUXEO_ARCHIVE_URL=("http://qa.nuxeo.org/jenkins/job/IT-nuxeo-master-build/"
                           "lastSuccessfulBuild/artifact/archives/")
DEFAULT_LESSMSI_URL="http://lessmsi.googlecode.com/files/lessmsi-v1.0.8.zip"
DEFAULT_ARCHIVE_PATTERN=r"nuxeo-cap-\d\.\d-I\d+_\d+-tomcat\.zip"
NUXEO_FOLDER='nuxeo-tomcat'
LESSMSI_FOLDER='lessmsi'
EXTRACTED_MSI_FOLDER='nxdrive_msi'


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
        description="Launch integration tests on Windows")

    parser.add_argument("--msi", default=DEFAULT_MSI)
    parser.add_argument("--nuxeo-archive-url",
                        default=DEFAULT_NUXEO_ARCHIVE_URL)
    parser.add_argument("--lessmsi-url", default=DEFAULT_LESSMSI_URL)

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
                           % (prefix, suffix, msi_filename))
    files.sort()
    return os.path.join(folder, files[-1])


def setup_nuxeo(nuxeo_archive_url):
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

    pflush("Finding latest nuxeo ZIP archive at: " + nuxeo_archive_url)
    index_html = urllib2.urlopen(nuxeo_archive_url).read()
    archive_pattern = re.compile(DEFAULT_ARCHIVE_PATTERN)
    filenames = archive_pattern.findall(index_html)
    if not filenames:
        raise ValueError("Could not find ZIP archives on "
                         + nuxeo_archive_url)
    filenames.sort()
    filename = filenames[0]
    url = nuxeo_archive_url + filename
    if not os.path.exists(filename):
        # the latest version does not exist but old versions might, let's delete
        # them to save some disk real estate in the workspace hosted on the CI
        # servers
        for old_filename in os.listdir('.'):
            if archive_pattern.match(old_filename):
                pflush("Deleting old archive: " + old_filename)
                os.unlink(old_filename)

    download(url, filename)
    unzip(filename)

    nuxeo_folder = filename[:-len(".zip")]
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
        else:
            shutil.rmtree(NUXEO_FOLDER)

    pflush("Renaming %s to %s" % (nuxeo_folder, NUXEO_FOLDER))
    os.rename(nuxeo_folder, NUXEO_FOLDER)
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


def extract_msi(lessmsi_url, msi_filename):
    if os.path.isdir(msi_filename):
        msi_filename = find_latest(msi_filename, suffix='.msi')

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


def run_tests_from_msi():
    ndrive = os.path.join(EXTRACTED_MSI_FOLDER, 'SourceDir', 'ndrive.exe')
    execute(ndrive + " test")

def run_tests_from_source():
    execute("cd nuxeo-drive-client && nosetests")


if __name__ == "__main__":
    options = parse_args()
    setup_nuxeo(options.nuxeo_archive_url)
    set_environment()
    if sys.platform == 'win32':
        extract_msi(options.lessmsi_url, options.msi)
        run_tests_from_msi()
    else:
        run_tests_from_source()
