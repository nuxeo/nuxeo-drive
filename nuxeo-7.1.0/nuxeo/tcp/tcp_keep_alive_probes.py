# coding: utf-8
"""
Inspired from https://github.com/finbourne/lusid-sdk-python/blob/ef029ec/sdk/lusid/tcp/tcp_keep_alive_probes.py
See NXPY-183 and linked tickets for details.
"""
import socket

from requests.adapters import HTTPAdapter
from urllib3 import HTTPSConnectionPool, PoolManager

from ..constants import LINUX, MAC, TCP_KEEPINTVL, TCP_KEEPIDLE, WINDOWS


class TCPKeepAliveValidationMethods(object):
    """
    This class contains a single method whose sole purpose is to set up TCP keep-alive probes on the socket for a
    connection. This is necessary for long running requests which will be silently terminated by the AWS Network Load
    Balancer which kills a connection if it is idle for more then 350 seconds.
    """

    __slots__ = ()

    @staticmethod
    def adjust_connection_socket(conn):
        """Adjusts the socket settings so that the client sends a TCP keep-alive probe over the connection."""

        sock = conn.sock

        if LINUX:
            # https://tldp.org/HOWTO/html_single/TCP-Keepalive-HOWTO/#setsockopt
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, TCP_KEEPIDLE)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, TCP_KEEPINTVL)
            # Number of times keep-alives are repeated before a close when there is no response
            #   Note 1: defaults to 10 on Windows, cannot be changed
            #   Note 2: defaults to 8 on macOS, cannot be changed since Catalina (sysctl net.inet.tcp.keepcnt)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 8)
        elif MAC:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            # 0x10 = TCP_KEEPALIVE (https://opensource.apple.com/source/xnu/xnu-6153.141.1/bsd/netinet/tcp.h.auto.html)
            sock.setsockopt(socket.IPPROTO_TCP, 0x10, TCP_KEEPINTVL)
        elif WINDOWS:
            # The Windows API requires milliseconds,
            # that's why the "* 1000" as TCP_* constants are expressed in seconds
            opt = (1, TCP_KEEPIDLE * 1000, TCP_KEEPINTVL * 1000)
            sock.ioctl(socket.SIO_KEEPALIVE_VALS, opt)


class TCPKeepAliveHTTPSConnectionPool(HTTPSConnectionPool):
    """
    This class overrides the _validate_conn method in the HTTPSConnectionPool class. This is the entry point to use
    for modifying the socket as it is called after the socket is created and before the request is made.
    """

    def _validate_conn(self, conn):
        """Called right before a request is made, after the socket is created."""
        super()._validate_conn(conn)
        TCPKeepAliveValidationMethods.adjust_connection_socket(conn)


class TCPKeepAlivePoolManager(PoolManager):
    """
    This pool manager has only had the *pool_classes_by_scheme* variable changed.
    This now points at our custom connection pools rather than the default connection pools.
    """

    def __init__(self, num_pools=10, headers=None, **connection_pool_kw):
        super().__init__(num_pools=num_pools, headers=headers, **connection_pool_kw)
        self.pool_classes_by_scheme = {
            "https": TCPKeepAliveHTTPSConnectionPool,
        }


class TCPKeepAliveHTTPSAdapter(HTTPAdapter):
    """"Transport adapter that allows us to set TCP keep-alive options."""

    def init_poolmanager(self, connections, maxsize, **pool_kwargs):
        """Override the default pool manager."""
        self.poolmanager = TCPKeepAlivePoolManager(
            num_pools=connections, maxsize=maxsize, **pool_kwargs
        )
