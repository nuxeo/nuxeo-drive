"""
NXDRIVE-961: We need to be strong against any update process regressions.

That fully automated script will:

1. generate an executable for a given version lesser than the current one,
   let's say 1.2.2 if the current version is 1.2.3
2. start un local webserver containing all required files for a complete upgrade
3. starts the executable using the local webserver as beta update canal
4. start Drive and let the auto-upgrade working
5. check that the Drive version is 1.2.3

Notes:

- It will purge any existent local installation, be warned!
- Ideally, no sync root are enabled on the local server for the Administrator account.
- FORCE_USE_LATEST_VERSION envar can be used to bypass the need for an account.

It __must__ be launched before any new release to validate the update process.
"""

import distutils.dir_util
import distutils.version
import hashlib
import http.server
import os
import os.path
import re
import shutil
import socketserver
import stat
import subprocess
import sys
import tempfile
import threading
import time
from os.path import expanduser, expandvars
from pathlib import Path

import requests
import yaml

# Alter the lookup path to be able to find Nuxeo Drive sources
sys.path.insert(0, os.getcwd())

__version__ = "4.0.0"

EXT = {"darwin": "dmg", "linux": "appimage", "win32": "exe"}[sys.platform]
Server = http.server.SimpleHTTPRequestHandler


def create_versions(dst, version):
    """Create the versions.yml file."""

    ext = "-x86_64.AppImage" if EXT == "appimage" else f".{EXT}"
    name = f"nuxeo-drive-{version}{ext}"
    path = os.path.join(dst, "alpha", name)
    with open(path, "rb") as installer:
        checksum = hashlib.sha256(installer.read()).hexdigest()
    print(">>> Computed the checksum:", checksum, flush=True)

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
    print(">>> Crafting versions.yml:", yml, flush=True)
    with open(os.path.join(dst, "versions.yml"), "a") as versions:
        versions.write(yml)


def download_last_ga_release(output_dir, version):
    """Download the latest GA release from the update website."""

    file = f"nuxeo-drive-{version}"
    file += "-x86_64.AppImage" if EXT == "appimage" else f".{EXT}"
    url = f"https://community.nuxeo.com/static/drive-updates/release/{file}"
    output = os.path.join(output_dir, "alpha", file)
    headers = {"User-Agent": f"check-updater/{__version__}"}
    print(">>> Downloading", url, "->", output, flush=True)

    with requests.get(url, headers=headers) as req, open(output, "wb") as dst:
        dst.write(req.content)

    # Adjust execution rights
    os.chmod(output, os.stat(output).st_mode | stat.S_IXUSR)

    return output


def gen_exe():
    """Generate an executable to install."""

    cmd = []

    if EXT == "appimage":
        cmd = "sh tools/linux/deploy_ci_agent.sh --build"
    elif EXT == "dmg":
        cmd = "sh tools/osx/deploy_ci_agent.sh --build"
    else:
        cmd = (
            "powershell -ExecutionPolicy Unrestricted"
            ' . ".\\tools\\windows\\deploy_ci_agent.ps1" -build'
        )

    print(">>> Command:", cmd, flush=True)
    subprocess.check_call(cmd.split())


def get_last_version_number():
    """Get the latest GA release version from the update website."""

    from nxdrive.updater.utils import get_latest_version

    url = "https://community.nuxeo.com/static/drive-updates/versions.yml"
    headers = {"User-Agent": f"check-updater/{__version__}"}
    print(">>> Downloading", url, flush=True)
    with requests.get(url, headers=headers) as req:
        data = req.content

    versions = yaml.safe_load(data)
    return get_latest_version(versions, "release")


def get_version():
    """Get the current version from the auto-generated VERSION file."""

    if EXT == "exe":
        file = expandvars("C:\\Users\\%username%\\.nuxeo-drive\\VERSION")
    else:
        file = expanduser("~/.nuxeo-drive/VERSION")

    with open(file) as f:
        return f.read().strip()


def install_drive(installer):
    """Install Drive onto the system to simulate a real case."""

    if EXT == "appimage":
        # Nothing to install on GNU/Linux
        pass
    elif EXT == "dmg":
        # Simulate what nxdrive.updater.darwin.install() does
        cmd = ["hdiutil", "mount", installer]
        print(">>> Command:", cmd, flush=True)
        mount_info = subprocess.check_output(cmd).decode("utf-8").strip()
        mount_dir = mount_info.splitlines()[-1].split("\t")[-1]

        src = "{}/Nuxeo Drive.app".format(mount_dir)
        dst = f"{Path.home()}/Applications/Nuxeo Drive.app"
        if os.path.isdir(dst):
            print(">>> Deleting", dst, flush=True)
            shutil.rmtree(dst)
        print(">>> Copying", src, "->", dst, flush=True)
        shutil.copytree(src, dst)

        cmd = ["hdiutil", "unmount", mount_dir]
        print(">>> Command:", cmd, flush=True)
        subprocess.check_call(cmd)
    else:
        cmd = [installer, "/verysilent"]
        print(">>> Command:", cmd, flush=True)
        subprocess.check_call(cmd)


def launch_drive(executable, args=None):
    """Launch Drive and wait for auto-update."""

    # Be patient, especially on Windows ...
    time.sleep(5)

    if not args:
        args = []

    if EXT == "appimage":
        cmd = [executable, *args]
    elif EXT == "dmg":
        cmd = ["open", f"{Path.home()}/Applications/Nuxeo Drive.app"]
        if args:
            cmd.append("--args")
            cmd.extend(args)
    else:
        cmd = [
            expandvars(
                "C:\\Users\\%username%\\AppData\\Local\\Nuxeo Drive\\ndrive.exe"
            ),
            *args,
        ]

    print(">>> Command:", cmd, flush=True)
    subprocess.check_call(cmd)


def cat_log():
    """Cat the log file."""

    if EXT == "exe":
        src = expandvars("C:\\Users\\%username%\\.nuxeo-drive\\logs\\nxdrive.log")
    else:
        src = expanduser("~/.nuxeo-drive/logs/nxdrive.log")

    print("", flush=True)
    print("", flush=True)
    print(">>> $ cat", src, flush=True)
    with open(src, encoding="utf-8") as fh:
        print(fh.read(), flush=True)
        print("", flush=True)
        print("", flush=True)


def set_options():
    """Set given options into the config file."""

    if EXT == "exe":
        home = expandvars("C:\\Users\\%username%\\.nuxeo-drive")
        file = f"{home}\\config.ini"
        metrics = f"{home}\\metrics.state"
    else:
        home = expanduser("~/.nuxeo-drive")
        file = f"{home}/config.ini"
        metrics = f"{home}/metrics.state"

    options = [
        "channel = alpha",
        "log-level-file = DEBUG",
        "exec-profile = private",
        "synchronization-enabled = False",
        "sync-and-quit = True",
        "update-check-delay = 8",
        "update-site-url = http://localhost:8000",
    ]

    if not os.path.isdir(home):
        os.mkdir(home)

    print(">>> Setting metrics: sentry", flush=True)
    with open(metrics, "w") as f:
        f.write("sentry\n")

    print(">>> Setting options:", options, flush=True)
    with open(file, "w") as f:
        f.write("[DEFAULT]\n")
        f.write("env = automatic\n")
        f.write("[automatic]\n")
        f.write("\n".join(options))
        f.write("\n")


def tests():
    """Simple tests before doing anything."""

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
    """Remove Drive from the computer."""

    if EXT == "appimage":
        # Nothing to uninstall on GNU/Linux"
        home = expanduser("~/.nuxeo-drive")
    elif EXT == "dmg":
        home = expanduser("~/.nuxeo-drive")
        path = f"{Path.home()}/Applications/Nuxeo Drive.app"
        if os.path.isdir(path):
            print(">>> Deleting", path, flush=True)
            shutil.rmtree(path)
    else:
        home = expandvars("C:\\Users\\%username%\\.nuxeo-drive")
        cmd = [
            expandvars(
                "C:\\Users\\%username%\\AppData\\Local\\Nuxeo Drive\\unins000.exe"
            ),
            "/verysilent",
        ]
        if os.path.isfile(cmd[0]):
            print(">>> Command:", cmd, flush=True)
            subprocess.check_call(cmd)

    # Purge local files
    if os.path.isdir(home):
        print(">>> Deleting", home, flush=True)
        shutil.rmtree(home)


def version_decrement(version):
    """Guess the lower version of the one given."""

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
                version = re.findall(r'"(.+)"', line)[0]
                print(">>> Current version is", version, "at line", lineno, flush=True)
                return version, lineno


def version_update(version, lineno):
    """Update Drive version."""

    path = os.path.join("nxdrive", "__init__.py")

    with open(path, encoding="utf-8") as handler:
        content = handler.readlines()

    content[lineno] = f'__version__ = "{version}"\n'

    with open(path, "w", encoding="utf-8", newline="\n") as handler:
        handler.write("".join(content))


def webserver(folder, port=8000):
    """Start a local web server."""

    def stop(server):
        """Stop the server after 60 seconds."""
        time.sleep(60)
        try:
            server.shutdown()
        except Exception:
            pass

    os.chdir(folder)

    httpd = socketserver.TCPServer(("", port), Server)
    print(">>> Serving", folder, f"at http://localhost:{port}", flush=True)
    print(">>> CTRL+C to terminate (or wait 60 sec)", flush=True)
    try:
        threading.Thread(target=stop, args=(httpd,)).start()
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    except Exception:
        pass


#
# Functions used by main()
# (or put like this: this is main() splited into smaller functions :)
#


def check_against_me(root):
    """Check the auto-updater against itself."""
    version, lineno = version_find()

    # Guess the anterior version
    previous = version_decrement(version)

    try:
        # Update the version in Drive code source to emulate an old version
        version_update(previous, lineno)
        assert version_find() == (previous, lineno)

        # No need to build Windows addons for the version N-1
        os.environ["SKIP_ADDONS"] = "1"

        exe = generate_installer(root, previous, move=True)

        # And gooo!
        job(root, version, exe, previous, "dev")
    finally:
        # Restore the original version
        version_update(version, lineno)


def check_against_last_release(root):
    """Check the auto-updater against the latest GA release."""

    version, _ = version_find()

    # Get the version number
    ga_version = get_last_version_number()

    # Get the latest GA release file
    last_ga = download_last_ga_release(root, ga_version)

    # Append the versions.yml file
    create_versions(root, ga_version)

    # And gooo!
    job(root, version, last_ga, ga_version, "ga")


def generate_installer(root, version, move=False):
    """Generate the installer for a given version and copy/move it to the web server root."""

    # Generate the installer
    gen_exe()

    # Copy or move all files to the webserver
    dst_folder = os.path.join(root, "alpha")
    ext = "-x86_64.AppImage" if EXT == "appimage" else f".{EXT}"
    dst_file = os.path.join(dst_folder, os.path.basename(f"nuxeo-drive-{version}{ext}"))

    func = shutil.move if move else shutil.copy
    for file in Path("dist").glob(f"nuxeo-drive-{version}*"):
        print(">>>", func.__name__.title(), file, "->", dst_folder, flush=True)
        func(str(file), dst_folder)

    # Create, or append to, the versions.yml file
    create_versions(root, version)

    return dst_file


def job(root, version, executable, previous_version, name):
    """Repetitive tasks.
    *name* is a string to customize the log file to archive.
    """

    src = os.getcwd()

    try:
        # Install Drive on the computer
        install_drive(executable)

        # Set the sync-and-stop option to let Drive update and quit without manual action
        set_options()

        version_forced = os.getenv("FORCE_USE_LATEST_VERSION", "0") == "1"
        if not version_forced:
            # Where the account will be bound
            local_folder = os.path.join(root, "folder")

            # Add an account to be able to auto-update
            url = os.getenv("NXDRIVE_TEST_NUXEO_URL", "http://localhost:8080/nuxeo")
            username = os.getenv("NXDRIVE_TEST_USERNAME", "Administrator")
            password = os.getenv("NXDRIVE_TEST_PASSWORD", "Administrator")
            launch_drive(
                executable,
                [
                    "bind-server",
                    username,
                    url,
                    f"--password={password}",
                    f"--local-folder={local_folder}",
                ],
            )

        # Launch Drive in its own thread
        print(">>> Testing upgrade", previous_version, "->", version, flush=True)
        threading.Thread(target=launch_drive, args=(executable,)).start()

        # Start the web server
        webserver(root)

        # Display the log file
        cat_log()

        # And assert the version is the good one
        current_ver = get_version()
        print(f">>> Current version is {current_ver!r}", flush=True)
        assert (
            current_ver == version
        ), f"Current version is {current_ver!r} (need {version})"
    finally:
        os.chdir(src)

        if not version_forced:
            # Remove the account
            try:
                launch_drive(executable, ["clean-folder", f"--local-folder={root}"])
            except Exception as exc:
                print(" !! ERROR:", exc, flush=True)

        # Remove the installation
        uninstall_drive()


def setup():
    """Setup and cleanup."""

    # Cleanup
    if os.path.isdir("dist"):
        shutil.rmtree("dist")

    # Remove previous installation
    uninstall_drive()

    # Server tree
    root = tempfile.mkdtemp()
    path = os.path.join(root, "alpha")
    os.makedirs(path)

    return root


def main():
    """Main logic."""

    root = setup()

    # Generate the current version executable
    version, _ = version_find()
    generate_installer(root, version)

    try:
        check_against_me(root)
        # To enable on all OS when 4.4.0 is GA
        # check_against_last_release(root)
    finally:
        # Cleanup
        try:
            shutil.rmtree(root)
        except Exception as exc:
            print(" !! ERROR:", exc, flush=True)


if __name__ == "__main__":
    tests()
    sys.exit(main())
