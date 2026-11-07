"""Unit tests for the HTTP client's redirect allowlist (no network)."""

from __future__ import annotations

import unittest

from palmeiras_monitor.sources.http_client import HttpClient


class RedirectAllowlistTests(unittest.TestCase):
    def test_allows_official_hosts(self) -> None:
        client = HttpClient()
        client.check_host("https://www.palmeiras.com.br/wp-json/wp/v2/posts")
        client.check_host("https://palmeiras.com.br/noticias/x/")

    def test_blocks_unknown_host(self) -> None:
        client = HttpClient()
        with self.assertRaises(RuntimeError):
            client.check_host("https://evil.example.com/redirect")

    def test_blocks_internal_host(self) -> None:
        client = HttpClient()
        with self.assertRaises(RuntimeError):
            client.check_host("http://127.0.0.1:8080/")

    def test_custom_allowlist(self) -> None:
        client = HttpClient(allowed_hosts={"example.org"})
        with self.assertRaises(RuntimeError):
            client.check_host("https://www.palmeiras.com.br/")


if __name__ == "__main__":
    unittest.main()
