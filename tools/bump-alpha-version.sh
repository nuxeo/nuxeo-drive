#!/bin/bash
#
# Bump the current version using the number of commits since the previous release.
#

set -e

bump() {
    local alpha_version
    local drive_version

    alpha_version="$(git describe --always --match="release-*" | cut -d"-" -f3)"
    drive_version="$(grep __version__ nxdrive/__init__.py | cut -d'"' -f2)"

    echo ">>> [alpha] Update information to ${drive_version}.${alpha_version}"
    sed -i s"/^__version__ = \".*\"/__version__ = \"${drive_version}.${alpha_version}\"/" nxdrive/__init__.py \
        || sed -i "" "s/^__version__ = \".*\"/__version__ = \"${drive_version}.${alpha_version}\"/" nxdrive/__init__.py  # macOS
    sed -i s"/^Release date: \`.*\`/Release date: \`$(date '+%Y-%m-%d')\`/" "docs/changes/${drive_version}.md" \
        || sed -i "" "s/^Release date: \`.*\`/Release date: \`$(date '+%Y-%m-%d')\`/" "docs/changes/${drive_version}.md"  # macOS

    git add nxdrive/__init__.py
    git add "docs/changes/${drive_version}.md"
    git commit -m "Bump version to ${drive_version}.${alpha_version}"
}

if [ "${RELEASE_TYPE:-unset}" = "alpha" ]; then
    bump
fi

exit 0
