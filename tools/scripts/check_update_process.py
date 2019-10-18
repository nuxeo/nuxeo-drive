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
import os
import os.path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import suppress
from os.path import expanduser
from pathlib import Path

__version__ = "0.4.1"


EXT = {"darwin": "dmg", "linux": "appimage", "win32": "exe"}[sys.platform]
Server = http.server.SimpleHTTPRequestHandler


def create_versions(dst, version):
    """ Create the versions.yml file. """

    ext = "-x86_64.AppImage" if EXT == "appimage" else f".{EXT}"
    name = f"nuxeo-drive-{version}{ext}"
    path = os.path.join(dst, "alpha", name)
    with open(path, "rb") as installer:
        checksum = hashlib.sha256(installer.read()).hexdigest()
    print(">>> Computed the checksum:", checksum)

    print(">>> Crafting versions.yml")
    """
    Note that we removed the following section with NXDRIVE-1419:

    min_all:
        "7.10": "7.10-HF47"
        "8.10": "8.10-HF38"
        "9.10": "9.10-HF20"
        "10.3": "10.3-SNAPSHOT"
        "10.10": "10.10-SNAPSHOT"
    """
    yml = f"""
"{version}":
    min: "7.10"
    type: alpha
    checksum:
        algo: sha256
        appimage: {checksum}
        dmg: {checksum}
        exe: {checksum}
    """
    with open(os.path.join(dst, "versions.yml"), "a") as versions:
        versions.write(yml)


def gen_exe():
    """ Generate an executable to install. """

    cmd = []

    if EXT == "appimage":
        cmd = "sh tools/linux/deploy_jenkins_slave.sh --build"
    elif EXT == "dmg":
        cmd = "sh tools/osx/deploy_jenkins_slave.sh --build"
    else:
        cmd = (
            "powershell -ExecutionPolicy Unrestricted"
            ' . ".\\tools\\windows\\deploy_jenkins_slave.ps1" -build'
        )

    print(">>> Command:", cmd)
    subprocess.check_call(cmd.split())


def install_drive(installer):
    """ Install Drive onto the system to simulate a real case. """

    if EXT == "appimage":
        # Nothing to install on GNU/Linux
        pass
    elif EXT == "dmg":
        # Simulate what nxdrive.updater.darwin.intall() does
        cmd = ["hdiutil", "mount", installer]
        print(">>> Command:", cmd)
        mount_info = subprocess.check_output(cmd).decode("utf-8").strip()
        mount_dir = mount_info.splitlines()[-1].split("\t")[-1]

        src = "{}/Nuxeo Drive.app".format(mount_dir)
        dst = f"{Path.home()}/Applications/Nuxeo Drive.app"
        if os.path.isdir(dst):
            print(">>> Deleting", dst)
            shutil.rmtree(dst)
        print(">>> Copying", src, "->", dst)
        shutil.copytree(src, dst)

        cmd = ["hdiutil", "unmount", mount_dir]
        print(">>> Command:", cmd)
        subprocess.check_call(cmd)
    else:
        cmd = [installer, "/verysilent"]
        print(">>> Command:", cmd)
        subprocess.check_call(cmd)


def launch_drive(executable):
    """ Launch Drive and wait for auto-update. """

    # Be patient, especially on Windows ...
    time.sleep(5)

    cmd = []

    if EXT == "appimage":
        cmd = [executable]
    elif EXT == "dmg":
        cmd = ["open", f"{Path.home()}/Applications/Nuxeo Drive.app", "--args"]
    else:
        cmd = [expanduser("~\\AppData\\Local\\Nuxeo Drive\\ndrive.exe")]

    cmd += [
        "--log-level-console=DEBUG",
        "--update-site-url=http://localhost:8000",
        "--update-check-delay=12",
        "--channel=alpha",
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
    assert version_decrement("1.2.333.4") == "1.2.333.3"
    assert version_decrement("1.2.333.0") == "1.2.332.0"
    assert version_checker(version_decrement("1.0.0"))
    assert version_checker(version_decrement("2.5.0"))
    assert version_checker(version_decrement("1.2.3"))
    assert version_checker(version_decrement("1.2.333"))
    return 1


def uninstall_drive():
    """ Remove Drive from the computer. """

    if EXT == "appimage":
        # Nothing to uninstall on GNU/Linux"
        pass
    elif EXT == "dmg":
        path = f"{Path.home()}/Applications/Nuxeo Drive.app"
        if os.path.isdir(path):
            print(">>> Deleting", path, flush=True)
            shutil.rmtree(path)
    else:
        cmd = [
            expanduser("~\\AppData\\Local\\Nuxeo Drive\\unins000.exe"),
            "/verysilent",
        ]
        if not os.path.isfile(cmd[0]):
            return
        print(">>> Command:", cmd)
        subprocess.check_call(cmd)


def version_decrement(version):
    """ Guess the lower version of the one given. """

    major, minor, patch, *dev = map(int, version.split("."))

    if dev:
        dev[0] -= 1
        if dev[0] < 0:
            dev[0] = 0
            patch -= 1
    else:
        patch -= 1

    if patch < 0:
        patch = 9
        minor -= 1
    if minor < 0:
        minor = 9
        major -= 1

    numbers = [major, minor, patch]
    if dev:
        numbers.append(dev[0])

    return ".".join(map(str, numbers))


def version_find():
    """
    Find the current Drive version.

    :return tuple: The version and line number where it is defined.
    """

    path = os.path.join("nxdrive", "__init__.py")
    with open(path, encoding="utf-8") as handler:
        for lineno, line in enumerate(handler.readlines()):
            if line.startswith("__version__"):
                return re.findall(r'"(.+)"', line)[0], lineno


def version_update(version, lineno):
    """ Update Drive version. """

    path = os.path.join("nxdrive", "__init__.py")

    with open(path, encoding="utf-8") as handler:
        content = handler.readlines()

    content[lineno] = f'__version__ = "{version}"\n'

    with open(path, "w", encoding="utf-8", newline="\n") as handler:
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

    # Cleanup
    with suppress(OSError):
        shutil.rmtree("dist")

    # Remove previous installation
    uninstall_drive()

    version_checker = distutils.version.StrictVersion
    src = os.getcwd()

    # Server tree
    root = tempfile.mkdtemp()
    path = os.path.join(root, "alpha")
    os.makedirs(path)

    # Generate the current version executable
    version, lineno = version_find()
    print(">>> Current version is", version, "at line", lineno)
    assert version_checker(version)
    gen_exe()

    # Move the file to the webserver
    ext = "-x86_64.AppImage" if EXT == "appimage" else f".{EXT}"
    file = f"dist/nuxeo-drive-{version}{ext}"
    dst_file = os.path.join(path, os.path.basename(file))
    print(">>> Moving", file, "->", path)
    shutil.move(file, dst_file)

    # Guess the anterior version
    previous = version_decrement(version)
    assert version_checker(previous)

    # Create the versions.yml file
    create_versions(root, version)

    try:
        # Update the version in Drive code source to emulate an old version
        version_update(previous, lineno)
        assert version_find() == (previous, lineno)

        # Generate the executable
        gen_exe()

        # Move the file to test to the webserver
        ext = "-x86_64.AppImage" if EXT == "appimage" else f".{EXT}"
        src_file = f"dist/nuxeo-drive-{previous}{ext}"
        installer = os.path.basename(src_file)
        dst_file = os.path.join(path, installer)
        print(">>> Moving", src_file, "->", path)
        shutil.move(src_file, dst_file)

        # Append the versions.yml file
        create_versions(root, previous)

        # Install Drive on the computer
        install_drive(dst_file)

        # Launch Drive in its own thread
        print(">>> Testing upgrade", previous, "->", version)
        threading.Thread(target=launch_drive, args=(dst_file,)).start()

        # Start the web server
        webserver(root)
    finally:
        os.chdir(src)

        # Restore the original version
        version_update(version, lineno)

        # Cleanup
        with suppress(OSError):
            shutil.rmtree(root)

        uninstall_drive()


if __name__ == "__main__":
    exit(tests() and main())
