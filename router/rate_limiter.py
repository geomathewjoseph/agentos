"""Rate Limiter — Per-provider quota tracking for free API tiers.

Thread-safe singleton that tracks API calls per provider and enforces
per-minute rate limits to stay within free tier quotas.
"""

from __future__ import annotations

import time
import threading
from collections import defaultdict
from tools.logger import log

# Conservative per-provider per-minute limits (free tiers)
PROVIDER_RPM = {
    "groq": 30,
    "cerebras": 60,
    "sambanova": 20,
    "fireworks": 20,
    "openrouter": 50,
}


class RateLimiter:
    """Thread-safe per-provider rate limiter.

    Tracks API call timestamps per provider and blocks (sleeps) when
    the per-minute limit would be exceeded.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._calls = defaultdict(list)  # provider → [timestamps]
        self._daily = defaultdict(int)  # provider → count today
        self._daily_date = time.localtime().tm_yday  # Track day of year
        self._cleanup_interval = 300  # Cleanup every 5 minutes
        self._last_cleanup = time.time()

    def wait_if_needed(self, provider: str):
        """Block if the provider's RPM limit has been reached.

        Args:
            provider: Provider name (e.g., 'groq', 'cerebras')
        """
        rpm = PROVIDER_RPM.get(provider, 10)
        wait_time = 0
        with self._lock:
            now = time.time()
            # Daily reset check
            current_day = time.localtime().tm_yday
            if current_day != self._daily_date:
                self._daily.clear()
                self._daily_date = current_day

            # Periodic cleanup of unused providers
            if now - self._last_cleanup > self._cleanup_interval:
                self._cleanup_old_entries(now)
                self._last_cleanup = now

            window = [t for t in self._calls[provider] if now - t < 60]
            if len(window) >= rpm:
                wait_time = 60 - (now - window[0]) + 0.5
            self._calls[provider] = window + [time.time()]
            self._daily[provider] += 1
            
        if wait_time > 0:
            log(
                "rate_limiter",
                f"{provider}: RPM limit reached ({rpm}/min), waiting {wait_time:.1f}s",
                "warning",
            )
            time.sleep(wait_time)

    def _cleanup_old_entries(self, now: float):
        """Remove providers not used in the last hour."""
        to_remove = []
        for prov, timestamps in self._calls.items():
            if not timestamps or (now - timestamps[-1]) > 3600:
                to_remove.append(prov)
        for prov in to_remove:
            del self._calls[prov]
            if prov in self._daily:
                del self._daily[prov]

    def daily_usage(self) -> dict:
        """Return daily usage counts per provider."""
        return dict(self._daily)


# Singleton instance
limiter = RateLimiter()
