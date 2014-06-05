import sys
from esky.bdist_esky import bdist_esky as e_bdist_esky


class bdist_esky(e_bdist_esky):

    e_bdist_esky.user_options.append(
        ('create-zipfile=', None, "create zip file from esky freeze"))

    def initialize_options(self):
        e_bdist_esky.initialize_options(self)
        self.create_zipfile = False

    def _run(self):
        self._run_initialise_dirs()
        if self.pre_freeze_callback is not None:
            self.pre_freeze_callback(self)
        self._run_freeze_scripts()
        if self.pre_zip_callback is not None:
            self.pre_zip_callback(self)
        # Only create zip file from esky freeze if option is passed
        if self.create_zipfile:
            self._run_create_zipfile()

# Monkey-patch distutils to override bdist_esky command included in
# esky.bdist_esky.
sys.modules["distutils.command.bdist_esky"] = sys.modules["nx_esky"]
