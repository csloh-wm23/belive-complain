"""Prevent older and newer local BeLive processes sharing a port."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest

from server import LocalHTTPServer


class ServerBindingTests(unittest.TestCase):
    def test_another_http_server_cannot_share_the_live_listener(self):
        with LocalHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler) as first:
            with self.assertRaises(OSError):
                second = ThreadingHTTPServer(first.server_address, BaseHTTPRequestHandler)
                second.server_close()

    def test_released_listener_can_be_reopened(self):
        with LocalHTTPServer(('127.0.0.1', 0), BaseHTTPRequestHandler) as first:
            address = first.server_address
        with LocalHTTPServer(address, BaseHTTPRequestHandler) as replacement:
            self.assertEqual(replacement.server_address, address)
