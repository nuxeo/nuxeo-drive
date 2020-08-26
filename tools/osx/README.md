# Generating a DMG

## Generating the .DS_Store metadata file for the DMG layout

The `generate-dmg-ds-store.sh` must be run using an active OSX graphical
sessions. It uses AppleScript to dimension the window to 600 x 250 pixels, put
the `dmgbackground.png` in the `.background` folder of the module and place the
icon locations of the `Nuxeo Drive.app` folder and the `Applications` symlink.

Doing so makes OSX update a `.DS_Store` file (binary format). This file can
then be extracted from the volume and saved to be reused to actually generate
the final `dmg` file using `create-dmg.sh`. This second script does not require
and active graphical session hence can be run by the Jenkins agent managing the
`nuxeo-drive-dmg` job in charge of the generation of the `Nuxeo
Drive.dmg` package:

  https://qa.nuxeo.org/jenkins/job/other/job/nuxeo-drive-dmg/

## Background PNG Resolution

The `dmgbackground.svg` file is the source for the png file. Note that Inkscape
has a hardcoded export convention of using 90dpi in png exports while OSX
expects a 72dpi png file. Hence the need to rescale the Inkscape document size
by a 1.25 ratio.
