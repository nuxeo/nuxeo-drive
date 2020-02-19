# coding: utf-8
"""
[macOS] Automatic notarization of a given DMG.

Usage: python notarize DMG_FILE [NOTARIZATION_UUID]
"""

import os
import re
import subprocess
import sys
import time
from typing import List, Pattern, Tuple

BUNDLE_IDENTIFIER = os.getenv("BUNDLE_IDENTIFIER", "org.nuxeo.drive")
NOTARIZATION_USERNAME = os.getenv("NOTARIZATION_USERNAME", "")
NOTARIZATION_PASSWORD = os.getenv("NOTARIZATION_PASSWORD", "")


def ask_for_notarization_uid(file: str) -> str:
    """Upload the DMG and wait for its notarization UID.

    The command will return something like:

        2020-02-19 11:55:35.558 altool[47499:579329] No errors uploading '$file'.
        RequestUUID = hhhhhhhh-hhhh-hhhh-hhhh-hhhhhhhhhhhh

    And we are interested in the value of RequestUUID.
    """
    print(f">>> [notarization] Uploading {file!r}")
    print("    (it may take a while)")

    cmd = [
        "xcrun",
        "altool",
        "--notarize-app",
        "--primary-bundle-id",
        BUNDLE_IDENTIFIER,
        "--username",
        NOTARIZATION_USERNAME,
        "--password",
        NOTARIZATION_PASSWORD,
        "--file",
        file,
    ]

    output = call(cmd)
    matches = re.findall(r"RequestUUID = (.+)", output)
    return matches[0] if matches else ""


def wait_for_notarization(uid: str) -> Tuple[bool, str]:
    """Poll at regular interval for the final notarization status.

    The command will return something like:

        2020-02-19 12:00:03.423 altool[48572:584781] No errors getting notarization info.

        (when the process in ongoing)

        RequestUUID: hhhhhhhh-hhhh-hhhh-hhhh-hhhhhhhhhhhh
                Date: 2020-02-19 10:55:29 +0000
                Status: in progress
            LogFileURL: (null)

        (when the process is ongoing but failed quickly, should still wait for more information)

        RequestUUID: hhhhhhhh-hhhh-hhhh-hhhh-hhhhhhhhhhhh
                Date: 2020-02-19 10:55:29 +0000
                Status: in progress
            LogFileURL: (null)
        Status Code: 2
        Status Message: Package Invalid

        (when the process is done, but with error)

        RequestUUID: hhhhhhhh-hhhh-hhhh-hhhh-hhhhhhhhhhhh
                Date: 2020-02-19 10:55:29 +0000
                Status: invalid
            LogFileURL: https://osxapps-ssl.itunes.apple.com/itunes-assets/Enigma113/...
        Status Code: 2
        Status Message: Package Invalid

        (when the process is done with success)
        # TODO: complete when https://github.com/Legrandin/pycryptodome/issues/381 is done
    """
    print(f">>> [notarization] Waiting status for {uid!r}")
    print("    (it may take a while)")

    cmd = [
        "xcrun",
        "altool",
        "--notarization-info",
        uid,
        "--username",
        NOTARIZATION_USERNAME,
        "--passwor",
        NOTARIZATION_PASSWORD,
    ]
    status = "in progress"

    while "waiting":
        output = call(cmd)
        status = get_notarization_status(output)

        if status != "in progress":
            # This is it!
            break

        # The process may take a while
        print("    (new check in 30 seconds ... )")
        time.sleep(30)

    # Get the URL of the JSON report
    report_url = get_notarization_report(output)

    return status == "valid", report_url


def get_notarization_report(
    output: str, pattern: Pattern = re.compile(r"LogFileURL: (.+)")
) -> str:
    """Get the notarization report URL from a given *output*."""
    return re.findall(pattern, output)[0]


def get_notarization_status(
    output: str, pattern: Pattern = re.compile(r"Status: (.+)")
) -> str:
    """Get the notarization status from a given *output*."""
    return re.findall(pattern, output)[0]


def staple_the_notarization(file: str) -> None:
    """Staple the notarization to the DMG."""
    call(["xcrun", "stapler", "staple", "-v", file])
    print(">>> [notarization] Done with success ᕦ(ò_óˇ)ᕤ")


def call(cmd: List[str]) -> str:
    """Make a system call and retrieve its output from stdout and stderr."""
    return subprocess.check_output(cmd, encoding="utf-8", stderr=subprocess.STDOUT)


def download_report(uid: str, url: str) -> str:
    """Download a notarization report."""
    # Lazy import as it may not be needed most of the time :fingers-crossed:
    import requests

    output = f"report-{uid}.json"
    print(f">>> Downloading report to {output!r}")
    with requests.get(url) as req:
        with open(output, "w", encoding="utf-8") as ofile:
            ofile.write(req.text)
            return output


def main(file: str, uid: str = "") -> int:
    """Entry point."""

    if not uid:
        # This is a new DMG file to notarize
        uid = ask_for_notarization_uid(file)
        if not uid:
            print(" !! No notarization UUID found.")
            return 1

    is_valid, report_url = wait_for_notarization(uid)
    if not is_valid:
        report = download_report(uid, report_url)
        print(f" !! Notarization failed. Check {report!r}.")
        return 2

    staple_the_notarization(file)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
