#!/bin/bash -eu
#
# Download required external files.
# This is convenient to eat less network resources and being able to
# reproduct builds without network access. This will be precious
# in years when such files may disappear.
#
# Those files are used when crafting and checking the AppImage file.
#
# Created: 2019-10-18
#

COMMIT_REF="9db3779700474cb87cff32f1d6470047a9786936"

# Files list to remove from the AppImage
[ -f excludelist ] && rm -fv excludelist
wget "https://raw.githubusercontent.com/AppImage/pkg2appimage/${COMMIT_REF}/excludelist"
echo "" >> excludelist

# Script that checks the AppImage conformity
[ -f "appdir-lint.sh" ] && rm -fv "appdir-lint.sh"
wget "https://raw.githubusercontent.com/AppImage/pkg2appimage/${COMMIT_REF}/appdir-lint.sh"

# The tool to actually create the AppImage
[ -f "appimagetool-x86_64.AppImage" ] && rm -f "appimagetool-x86_64.AppImage"
wget "https://github.com/AppImage/AppImageKit/releases/download/12/appimagetool-x86_64.AppImage"
chmod -v a+x "appimagetool-x86_64.AppImage"
