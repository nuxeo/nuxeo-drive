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

import http.server
import socketserver
import distutils.dir_util
import distutils.version
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from os.path import expanduser

__version__ = "0.2.0"


EXT = {"darwin": "dmg", "win32": "exe"}.get(sys.platform)
Server = http.server.BaseHTTPRequestHandler


def create_versions(dst, version):
    """ Create the versions.yml file. """

    name = "nuxeo-drive-{version}.{ext}".format(version=version, ext=EXT)
    path = os.path.join(dst, "release", name)
    with open(path, "rb") as installer:
        checksum = hashlib.sha256(installer.read()).hexdigest()
    print(">>> Computed the checksum:", checksum)

    print(">>> Crafting versions.yml")
    yml = b"""
{version}:
    min: '7.10-HF11'
    type: release
    checksum:
        algo: sha256
        dmg: {checksum}
        exe: {checksum}
    """.format(
        version=version, checksum=checksum
    )
    with open(os.path.join(dst, "versions.yml"), "w") as versions:
        versions.write(yml)


def gen_exe():
    """ Generate an executable to install. """

    cmd = []

    if sys.platform == "darwin":
        cmd = "sh tools/osx/deploy_jenkins_slave.sh --build"
    elif sys.platform == "win32":
        cmd = (
            "powershell -ExecutionPolicy Unrestricted"
            ' . ".\\tools\\windows\\deploy_jenkins_slave.ps1" -build'
        )

    print(">>> Command:", cmd)
    output = subprocess.check_output(cmd.split())
    return output.decode("utf-8").strip()


def install_drive(installer):
    """ Install Drive onto the system to simulate a real case. """

    if sys.platform == "darwin":
        # Simulate what nxdrive.updater.darwin.intall() does
        cmd = ["hdiutil", "mount", installer]
        print(">>> Command:", cmd)
        mount_info = subprocess.check_output(cmd)
        mount_dir = mount_info.splitlines()[-1].split("\t")[-1]

        src = "{}/Nuxeo Drive.app".format(mount_dir)
        dst = "/Applications/Nuxeo Drive.app"
        if os.path.isdir(dst):
            print(">>> Deleting", dst)
            shutil.rmtree(dst)
        print(">>> Copying", src, "->", dst)
        shutil.copytree(src, dst)

        cmd = ["hdiutil", "unmount", mount_dir]
        print(">>> Command:", cmd)
        subprocess.check_call(cmd)
    elif sys.platform == "win32":
        cmd = [installer, "/verysilent"]
        print(">>> Command:", cmd)
        subprocess.check_call(cmd)


def launch_drive():
    """ Launch Drive and wait for auto-update. """

    # Be patient, especially on Windows ...
    time.sleep(5)

    cmd = []

    if sys.platform == "darwin":
        cmd = ["open", "/Applications/Nuxeo Drive.app", "--args"]
    elif sys.platform == "win32":
        cmd = [expanduser("~\\AppData\\Roaming\\Nuxeo Drive\\ndrive.exe")]

    cmd += [
        "--log-level-console=TRACE",
        "--update-site-url=http://localhost:8000",
        "--beta-update-site-url=http://localhost:8000",
    ]
    print(">>> Command:", cmd)
    return subprocess.check_output(cmd).decode("utf-8").strip()


def tests():
    """ Simple tests before doing anything. """

    version_checker = distutils.version.StrictVersion
    assert version_decrement("1.0.0") == "0.9.9"
    assert version_decrement("2.5.0") == "2.4.9"
    assert version_decrement("1.2.3") == "1.2.2"
    assert version_decrement("1.2.333") == "1.2.332"
    assert version_checker(version_decrement("1.0.0"))
    assert version_checker(version_decrement("2.5.0"))
    assert version_checker(version_decrement("1.2.3"))
    assert version_checker(version_decrement("1.2.333"))
    return 1


def uninstall_drive():
    """ Remove Drive from the computer. """

    if sys.platform == "darwin":
        path = "/Applications/Nuxeo Drive.app"
        print(">>> Deleting", path)
        try:
            shutil.rmtree(path)
        except OSError:
            pass
    elif sys.platform == "win32":
        cmd = [
            expanduser("~\\AppData\\Roaming\\Nuxeo Drive\\unins000.exe"),
            "/verysilent",
        ]
        print(">>> Command:", cmd)
        try:
            subprocess.check_call(cmd)
        except (WindowsError, subprocess.CalledProcessError):
            pass


def version_decrement(version):
    """ Guess the lower version of the one given. """

    major, minor, patch = map(int, version.split("."))

    patch -= 1
    if patch < 0:
        patch = 9
        minor -= 1
    if minor < 0:
        minor = 9
        major -= 1

    return ".".join(map(str, [major, minor, patch]))


def version_find():
    """
    Find the current Drive version.

    :return tuple: The version and line number where it is defined.
    """

    path = os.path.join("nxdrive", "__init__.py")
    with io.open(path, encoding="utf-8") as handler:
        for lineno, line in enumerate(handler.readlines()):
            if line.startswith("__version__"):
                return re.findall(r"'(.+)'", line)[0], lineno


def version_update(version, lineno):
    """ Update Drive version. """

    path = os.path.join("nxdrive", "__init__.py")

    with io.open(path, encoding="utf-8") as handler:
        content = handler.readlines()

    content[lineno] = "__version__ = '{}'\n".format(version)

    with io.open(path, "w", encoding="utf-8", newline="\n") as handler:
        handler.write("".join(content))


def webserver(folder, port=8000):
    """ Start a local web server. """

    os.chdir(folder)
    httpd = socketserver.TCPServer(("", port), Server)
    print(">>> Serving", folder, "at http://localhost:8000")
    print(">>> CTRL+C to terminate")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


def main():
    """ Main logic. """

    if sys.platform.startswith("linux"):
        print(">>> macOS and Windows only.")
        return 1

    # Cleanup
    try:
        shutil.rmtree("dist")
    except OSError:
        pass

    # Remove previous installation
    uninstall_drive()

    version_checker = distutils.version.StrictVersion
    src = os.getcwd()

    # Server tree
    root = tempfile.mkdtemp()
    path = os.path.join(root, "release")
    os.makedirs(path)

    # Generate the current version executable
    version, lineno = version_find()
    print(">>> Current version is", version, "at line", lineno)
    assert version_checker(version)
    gen_exe()

    # Move the file to the webserver
    file_ = "dist/nuxeo-drive-{}.{}".format(version, EXT)
    dst_file = os.path.join(path, os.path.basename(file_))
    print(">>> Moving", file_, "->", path)
    os.rename(file_, dst_file)

    # Create the versions.yml file
    create_versions(root, version)

    # Guess the anterior version
    previous = version_decrement(version)
    print(">>> Testing upgrade", previous, "->", version)
    assert version_checker(previous)

    try:
        # Update the version in Drive code source to emulate an old version
        version_update(previous, lineno)
        assert version_find() == (previous, lineno)

        # Generate the executable
        gen_exe()

        # Move the file to test to the webserver
        src_file = "dist/nuxeo-drive-{}.{}".format(previous, EXT)
        installer = os.path.basename(src_file)
        dst_file = os.path.join(path, installer)
        print(">>> Moving", src_file, "->", path)
        os.rename(src_file, dst_file)

        # Install Drive on the computer
        install_drive(dst_file)

        # Launch Drive in its own thread
        threading.Thread(target=launch_drive).start()

        # Start the web server
        webserver(root)
    finally:
        os.chdir(src)

        # Restore the original version
        version_update(version, lineno)

        # Cleanup
        try:
            shutil.rmtree(root)
        except OSError:
            pass

        uninstall_drive()


if __name__ == "__main__":
    exit(tests() and main())
