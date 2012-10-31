# Copyright 2012 - Mozilla Foundation
# Copyright 2012 - Benoit Chesneau
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Utilities to daemonize the process taken from circus

https://github.com/mozilla-services/circus/blob/master/circus/circusd.py#L34

"""
import os
try:
    import resource
except ImportError:
    # Do not fail to import under Windows
    pass

MAXFD = 1024

if hasattr(os, "devnull"):
    DEVNULL = os.devnull
else:
    DEVNULL = "/dev/null"


def get_maxfd():
    maxfd = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    if (maxfd == resource.RLIM_INFINITY):
        maxfd = MAXFD
    return maxfd



def closerange(fd_low, fd_high):
    """Failover implementation in case not provided in os"""
    # Iterate through and close all file descriptors.
    for fd in xrange(fd_low, fd_high):
        try:
            os.close(fd)
        except OSError:  # ERROR, fd wasn't open to begin with (ignored)
            pass


try:
    from os import closerange
except ImportError:
    # Use the failover implementation
    pass


def daemonize():
    """Detach the current process: following instructions will run as a daemon

    1- Fork
    2- Detach the child from the parent
    3- Redirect stdin/out/err streams to /dev/null
    4- Let the parent process exit

    Because of the fork, this operation should happen early in the process
    lifecyle, in particular before the instanciation of any sqlite session
    (i.e. before the instanciation of the Controller object) and also before
    the configuration of the logging module to avoid having to deal with file
    handlers.

    Under Windows this does nothing: instead of detaching the process one
    should use the ndrivew.exe that is a GUI windows exe that does not require
    a running cmd console hence can work as a daemon process from the desktop
    user point of view.

    """
    if os.name != 'posix':
        # Daemonization is a posix concept
        return

    if os.fork():
        os._exit(0)

    os.setsid()

    if os.fork():
        os._exit(0)

    os.chdir('/')
    os.umask(0)
    maxfd = get_maxfd()
    closerange(0, maxfd)

    os.open(DEVNULL, os.O_RDWR)
    os.dup2(0, 1)
    os.dup2(0, 2)
