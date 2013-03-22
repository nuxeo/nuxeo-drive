# Useful to launch an interactive debugging session in ipython with %ed or %run
from nxdrive.controller import Controller
from nxdrive.model import ServerBinding
c = Controller('~/.nuxeo-drive')
s = c.get_session()
sb = s.query(ServerBinding).one()


