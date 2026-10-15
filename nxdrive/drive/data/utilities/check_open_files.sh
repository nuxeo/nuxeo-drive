#!/usr/bin/env bash
#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

#
# Whether a file is currently open in another application.
#
#   check_open_files.sh <file-path> [pid-to-ignore]
#
# Prints TRUE, FALSE or UNKNOWN on stdout.
#
# UNKNOWN means no probe could answer, and must never be read as "closed": a
# wrong "closed" lets a download overwrite whatever the user has not saved,
# while a wrong "open" only costs a deferral.

set -u

if [ -z "${1:-}" ]; then
    echo "Usage: $0 <file-path> [pid-to-ignore]" >&2
    exit 1
fi

TARGET="$1"

# Drive's own PID. Its transfers hold the file briefly and would otherwise read
# as the user having it open.
IGNORE_PID="${2:-0}"

# Resolve to a canonical absolute path so symlinks match the /proc targets.
REAL_TARGET="$(readlink -f -- "${TARGET}" 2>/dev/null \
    || realpath -- "${TARGET}" 2>/dev/null \
    || echo "${TARGET}")"

if [ ! -e "${REAL_TARGET}" ]; then
    echo "FALSE"
    exit 0
fi

# Reads PIDs on stdin and succeeds if any of them is not ours.
holder_other_than_us() {
    local pid
    while read -r pid; do
        # fuser appends an access-type letter to each PID.
        pid="${pid//[!0-9]/}"
        [ -n "${pid}" ] || continue
        [ "${pid}" = "${IGNORE_PID}" ] && continue
        return 0
    done
    return 1
}

# 1. lsof, when installed. Not -b: it blocks the stat() lsof needs to identify
#    the file, so every lookup fails. A hang on an unreachable mount is bounded
#    by the caller's timeout instead.
if command -v lsof >/dev/null 2>&1; then
    if lsof -w -t -- "${REAL_TARGET}" 2>/dev/null | holder_other_than_us; then
        echo "TRUE"
        exit 0
    fi
fi

# 2. fuser, which some distributions ship without lsof.
if command -v fuser >/dev/null 2>&1; then
    if fuser -- "${REAL_TARGET}" 2>/dev/null | tr -s ' ' '\n' | holder_other_than_us; then
        echo "TRUE"
        exit 0
    fi
fi

# 3. /proc directly, which needs no external command at all. Neither tool above
#    can be trusted to say "nobody has it": both report failure and "no match"
#    the same way, so only this scan may answer FALSE.
scanned=false
for pid_dir in /proc/[0-9]*; do
    [ -d "${pid_dir}/fd" ] || continue
    scanned=true

    pid="${pid_dir##*/}"
    [ "${pid}" = "${IGNORE_PID}" ] && continue

    for fd in "${pid_dir}"/fd/*; do
        [ -L "${fd}" ] || continue
        link="$(readlink "${fd}" 2>/dev/null)"
        # Dropped when a file is unlinked while still held open.
        link="${link% (deleted)}"
        if [ "${link}" = "${REAL_TARGET}" ]; then
            echo "TRUE"
            exit 0
        fi
    done
done

if [ "${scanned}" = true ]; then
    echo "FALSE"
else
    echo "UNKNOWN"
fi
