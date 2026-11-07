"""HTTP client with retries, timeouts, and a browser-like User-Agent."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("palmeiras_monitor")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)


class HttpClient:
    """Small wrapper around httpx that retries transient failures."""

    def __init__(
        self,
        timeout: float = 25.0,
        attempts: int = 3,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.timeout = timeout
        self.attempts = attempts
        self.headers = {"User-Agent": user_agent, "Accept-Language": "pt-BR,pt;q=0.9"}

    def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                response = httpx.get(
                    url,
                    params=params,
                    headers=self.headers,
                    timeout=self.timeout,
                    follow_redirects=True,
                )
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
