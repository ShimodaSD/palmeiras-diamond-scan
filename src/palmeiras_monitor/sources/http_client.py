"""HTTP client with retries, timeouts, redirect allowlisting, and a browser-like User-Agent."""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger("palmeiras_monitor")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

# Only official Palmeiras hosts may be requested or reached through redirects.
ALLOWED_HOSTS = {"palmeiras.com.br", "www.palmeiras.com.br"}
MAX_REDIRECTS = 5


class HttpClient:
    """Small wrapper around httpx that retries transient failures."""

    def __init__(
        self,
        timeout: float = 25.0,
        attempts: int = 3,
        user_agent: str = DEFAULT_USER_AGENT,
        allowed_hosts: set[str] | None = None,
    ) -> None:
        self.timeout = timeout
        self.attempts = attempts
        self.headers = {"User-Agent": user_agent, "Accept-Language": "pt-BR,pt;q=0.9"}
        self.allowed_hosts = allowed_hosts or ALLOWED_HOSTS

    def check_host(self, url: str) -> None:
        """Raise when a URL does not point at an allowed official host."""
        host = (urlparse(url).hostname or "").lower()
        if host not in self.allowed_hosts:
            raise RuntimeError(f"Blocked request to non-official host: {host or url}")

    def _request(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        self.check_host(url)
        current = url
        current_params = params
        for _ in range(MAX_REDIRECTS + 1):
            response = httpx.get(
                current,
                params=current_params,
                headers=self.headers,
                timeout=self.timeout,
                follow_redirects=False,
            )
            if response.is_redirect:
                target = urljoin(current, response.headers.get("location", ""))
                self.check_host(target)
                current, current_params = target, None
                continue
            return response
        raise RuntimeError(f"Too many redirects for {url}")

    def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                response = self._request(url, params)
                response.raise_for_status()
                return response
            except Exception as exc:  # noqa: BLE001 - retry any transient failure
                last_error = exc
                logger.warning("GET %s attempt %s/%s failed: %s", url, attempt, self.attempts, exc)
                if attempt < self.attempts:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"GET {url} failed after {self.attempts} attempts") from last_error

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch a URL and decode the JSON response."""
        return self._get(url, params).json()

    def get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        """Fetch a URL and return its text body."""
        return self._get(url, params).text
