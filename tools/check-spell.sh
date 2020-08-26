#!/bin/bash

set -e

check_spell() {
    local to_skip=""

    echo "* Add '--interactive=3 --write-changes' arguments to the following command to allow interactive modifications."

    for file in tools/spell.skip .gitignore; do
        # Small santitization:
        #   - skip empty lines and comments
        #   - strip inline comments
        excludes="$(sed '/^\s*$/d ; /^#.*$/d ; s/\s*#.*$//' "${file}")"
        for line in ${excludes}; do
            # Codespell needs relative paths for folders
            [ -e "${line}" ] && line="./${line}"
            to_skip="${to_skip}${line},"
        done
    done

    # Display the command to allow interactive mode later
    set -x
    codespell \
        --ignore-words=tools/spell.allowlist \
        --quiet-level=4 \
        --skip="${to_skip}" \
        2> /dev/null
    set +x
}

check_spell
