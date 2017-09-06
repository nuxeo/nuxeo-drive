# coding: utf-8
"""
Esky extension.

Extends the 'bdist_esky' command with:

- the 'create-zipfile' option to allow not creating a zip file of the
esky freeze.

- the 'rm-freeze-dir-after-zipping' option to allow not removing the esky
freeze directory after zipping it if 'create-zipfile' is True.

"""

import os
import shutil
import sys

from esky.bdist_esky import bdist_esky as e_bdist_esky
from esky.util import create_zipfile, get_platform, really_rmtree


def fix_missing(self):
    if sys.platform != "win32":
        return

    appdata_dir =  os.path.join(
        self.bootstrap_dir,
        'appdata',
        os.path.basename(self.bootstrap_dir),
    )

    # Duplicate imageformats folder content in root directory
    shutil.copytree(os.path.join(appdata_dir, 'imageformats'),
                    os.path.join(self.bootstrap_dir, 'imageformats'))

    # Duplicate OpenSSL DDL
    shutil.copy(os.path.join(appdata_dir, 'libeay32.dll'), self.bootstrap_dir)
    shutil.copy(os.path.join(appdata_dir, 'ssleay32.dll'), self.bootstrap_dir)


class bdist_esky(e_bdist_esky):

    e_bdist_esky.user_options.append(
        ('create-zipfile=', None, "create zip file from esky freeze"))
    e_bdist_esky.user_options.append(
        ('rm-freeze-dir-after-zipping=', None, "remove esky freeze directory"
         " after zipping it"))

    def initialize_options(self):
        e_bdist_esky.initialize_options(self)
        self.create_zipfile = True
        self.pre_zip_callback = fix_missing
        self.rm_freeze_dir_after_zipping = True

    def _run(self):
        self._run_initialise_dirs()
        if self.pre_freeze_callback is not None:
            self.pre_freeze_callback(self)
        self._run_freeze_scripts()
        if self.pre_zip_callback is not None:
            self.pre_zip_callback(self)
        # Only create zip file from esky freeze if option is passed
        if self.create_zipfile and self.create_zipfile != 'False':
            self._run_create_zipfile()

    def _run_create_zipfile(self):
        """Zip up the final distribution."""
        print "zipping up the esky"
        fullname = self.distribution.get_fullname()
        platform = get_platform()
        zfname = os.path.join(self.dist_dir,
                              "%s.%s.zip" % (fullname, platform, ))
        if hasattr(self.freezer_module, "zipit"):
            self.freezer_module.zipit(self, self.bootstrap_dir, zfname)
        else:
            create_zipfile(self.bootstrap_dir, zfname, compress=True)
        # Only remove bootstrap dir if option is passed
        if (self.rm_freeze_dir_after_zipping
            and self.rm_freeze_dir_after_zipping != 'False'):
            really_rmtree(self.bootstrap_dir)

# Monkey-patch distutils to override bdist_esky command included in
# esky.bdist_esky.
sys.modules["distutils.command.bdist_esky"] = sys.modules["nx_esky"]
