r"""Setup the windows machine for Continuous Integration on the MSI package

This will:

    - download the latest nightly build of Nuxeo from Jenkins
    - deploy the server side package of nuxeo-drive (TODO)
    - start the server
    - setup test environment variables
    - download http://code.google.com/p/lessmsi if not already there
    - extract the MSI archive in a local, non system folder with lessmsi
    - launch the ``ndrive test`` command to run the integration tests
    - stop the server and collect the logs

Get the help on running this with::

    C:\Python27\python tools\windows\integration_tests_setup.py --help

"""

import os
import sys
import urllib2
import argparse
import re
import zipfile
import shutil
import atexit


DEFAULT_MSI = r"dist\nuxeo-drive-0.1.0-win32.msi"
DEFAULT_NUXEO_ARCHIVE_URL=("http://qa.nuxeo.org/jenkins/job/IT-nuxeo-master-build/"
                           "lastSuccessfulBuild/artifact/archives/")
DEFAULT_LESSMSI_URL="http://lessmsi.googlecode.com/files/lessmsi-v1.0.8.zip"
DEFAULT_ARCHIVE_PATTERN=r"nuxeo-cap-\d\.\d-I\d+_\d+-tomcat\.zip"
NUXEO_FOLDER='nuxeo-tomcat'
LESSMSI_FOLDER='lessmsi'
EXTRACTED_MSI_FOLDER='nxdrive_msi'


def execute(cmd):
    print "> " + cmd
    code = os.system(cmd)
    if code != 0:
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
        print "Downloading %s to %s" % (url, filename)
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
    print "Unzipping", filename
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


def setup_nuxeo(nuxeo_archive_url):
    try:
	java_home = os.environ['JAVA_HOME']
    except KeyError:
        raise RuntimeError('The JAVA_HOME env variable is required.')
    java_bin = os.path.join(java_home, 'bin')
    path = os.environ['PATH']
    if not java_bin in path:
	os.environ['PATH'] = path + ";" + java_bin

    print "Finding latest nuxeo ZIP archive at: " + nuxeo_archive_url
    index_html = urllib2.urlopen(nuxeo_archive_url).read()
    filenames = re.compile(DEFAULT_ARCHIVE_PATTERN).findall(index_html)
    if not filenames:
        raise ValueError("Could not find ZIP archives on "
                         + nuxeo_archive_url)
    filenames.sort()
    filename = filenames[0]
    url = nuxeo_archive_url + filename
    download(url, filename)
    unzip(filename)

    nuxeo_folder = filename[:-len(".zip")]
    print "Renaming %s to %s" % (nuxeo_folder, NUXEO_FOLDER)
    if os.path.exists(NUXEO_FOLDER):
        shutil.rmtree(NUXEO_FOLDER)
    os.rename(nuxeo_folder, NUXEO_FOLDER)
    with open(os.path.join(NUXEO_FOLDER, 'bin', 'nuxeo.conf'), 'wb') as f:
        f.write("\nnuxeo.wizard.done=true\n")

    print "Starting the Nuxeo server"
    nuxeoctl = os.path.join(NUXEO_FOLDER, 'bin', 'nuxeoctl')
    execute(nuxeoctl + " --gui false start")

    # Register a callback to stop the nuxeo server
    atexit.register(execute, nuxeoctl + " --gui false stop")


def extract_msi(lessmsi_url, msi_filename):
    filename = os.path.basename(lessmsi_url)
    if not os.path.exists(LESSMSI_FOLDER):
        download(lessmsi_url, filename)
        unzip(filename, target=LESSMSI_FOLDER)

    print "Extracting the MSI"
    lessmsi = os.path.join(LESSMSI_FOLDER, 'lessmsi')
    if os.path.exists(EXTRACTED_MSI_FOLDER):
	shutil.rmtree(EXTRACTED_MSI_FOLDER)
    execute("%s /x %s %s" % (lessmsi, msi_filename, EXTRACTED_MSI_FOLDER))


def run_tests():
    ndrive = os.path.join(EXTRACTED_MSI_FOLDER, 'SourceDir', 'ndrive.exe')
    os.environ['NXDRIVE_TEST_NUXEO_URL'] = "http://localhost:8080/nuxeo"
    os.environ['NXDRIVE_TEST_USER'] = "Administrator"
    os.environ['NXDRIVE_TEST_PASSWORD'] = "Administrator"
    execute(ndrive + " test")


if __name__ == "__main__":
    options = parse_args()
    setup_nuxeo(options.nuxeo_archive_url)
    extract_msi(options.lessmsi_url, options.msi)
    run_tests()
