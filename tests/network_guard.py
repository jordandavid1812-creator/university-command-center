"""Shared guard for AI tests: any attempt to resolve or reach a non-local address fails the test.

Use NoNetworkMixin as the first base class (before unittest.TestCase or a Django test case),
so stage 3b's web tests get the same guard as the provider client tests.
"""
import socket
from unittest.mock import patch

LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _refuse_non_local(original):
    def guarded(*args, **kwargs):
        target = args[1] if args and isinstance(args[0], socket.socket) else args[0]
        host = target[0] if isinstance(target, tuple) else target
        if host not in LOOPBACK:
            raise AssertionError(f"test tried to reach the network: {host!r}")
        return original(*args, **kwargs)
    return guarded


class NoNetworkMixin:
    def setUp(self):
        for target, name in ((socket.socket, "connect"), (socket, "create_connection"), (socket, "getaddrinfo")):
            patcher = patch.object(target, name, _refuse_non_local(getattr(target, name)))
            patcher.start()
            self.addCleanup(patcher.stop)
        super().setUp()
