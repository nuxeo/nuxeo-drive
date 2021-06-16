"""[macOS] Automatic notarization process.

Usage: python notarize FILE [NOTARIZATION_UUID]

If NOTARIZATION_UUID is given, then the noratization process will continue.
Else a new notarization process will be started
"""

import os
import re
import subprocess
import sys
import time
from typing import List, Pattern, Tuple

import requests

BUNDLE_IDENTIFIER = os.getenv("BUNDLE_IDENTIFIER", "org.nuxeo.drive")
NOTARIZATION_USERNAME = os.environ["NOTARIZATION_USERNAME"]
NOTARIZATION_PASSWORD = os.environ["NOTARIZATION_PASSWORD"]


def ask_for_notarization_uid(file: str) -> str:
    """Upload the *file* and wait for its notarization UUID.

    The command will return something like:

        2020-02-19 11:55:35.558 altool[47499:579329] No errors uploading '$file'.
        RequestUUID = hhhhhhhh-hhhh-hhhh-hhhh-hhhhhhhhhhhh

    And we are interested in the value of RequestUUID.
    """
    print(f">>> [notarization] Uploading {file!r}", flush=True)
    print("    (it may take a while)", flush=True)

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


def wait_for_notarization(uuid: str) -> Tuple[bool, str]:
    """Poll at regular interval for the final notarization status of the given *uuid*.

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

        RequestUUID: hhhhhhhh-hhhh-hhhh-hhhh-hhhhhhhhhhhh
                Date: 2020-02-19 10:55:29 +0000
                Status: success
            LogFileURL: https://osxapps-ssl.itunes.apple.com/itunes-assets/Enigma113/...
        Status Code: 0
        Status Message: Package Approved

    """
    print(f">>> [notarization] Waiting status for {uuid!r}", flush=True)
    print("    (it may take a while)", flush=True)

    # Small sleep to prevent "Error: Apple Services operation failed. Could not find the RequestUUID."
    time.sleep(10)

    cmd = [
        "xcrun",
        "altool",
        "--notarization-info",
        uuid,
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
        print("    (new check in 30 seconds ... )", flush=True)
        time.sleep(30)

    # Get the URL of the JSON report
    report_url = get_notarization_report(output)

    return status == "success", report_url


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
    """Staple the notarization to the *file*."""
    call(["xcrun", "stapler", "staple", "-v", file])
    print(">>> [notarization] Done with success ᕦ(ò_óˇ)ᕤ", flush=True)


def call(cmd: List[str]) -> str:
    """Make a system call and retrieve its output from stdout and stderr."""
    exitcode, output = subprocess.getstatusoutput(" ".join(cmd))
    if exitcode != 0:
        print(" !! ERROR", flush=True)
        print(output, flush=True)
        raise subprocess.CalledProcessError(exitcode, cmd)
    return output


def download_report(uuid: str, url: str) -> str:
    """Download a notarization report."""
    output = f"report-{uuid}.json"
    print(f">>> Downloading the report to {output}", flush=True)

    with requests.get(url) as req:
        with open(output, "w", encoding="utf-8") as ofile:
            ofile.write(req.text)
            return output


def main(file: str, uuid: str = "") -> int:
    """Entry point."""

    if not uuid:
        # This is a new DMG file to notarize
        uuid = ask_for_notarization_uid(file)
    if not uuid:
        print(" !! No notarization UUID found.", flush=True)
        return 1

    is_valid, report_url = wait_for_notarization(uuid)
    download_report(uuid, report_url)

    if not is_valid:
        print(" !! Notarization failed. Check the report for details.", flush=True)
        return 2

    staple_the_notarization(file)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
