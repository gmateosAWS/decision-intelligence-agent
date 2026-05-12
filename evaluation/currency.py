"""USD → EUR conversion via Frankfurter API with 1-hour cache (item 8.7.a)."""

from __future__ import annotations

import os
import time
from typing import Optional

_cached_rate: Optional[float] = None
_cache_ts: float = 0.0
_CACHE_TTL_S = 3600  # 1 hour

_FRANKFURTER_URL = "https://api.frankfurter.app/latest?from=USD&to=EUR"


def _env_fallback() -> Optional[float]:
    raw = os.environ.get("EUR_USD_RATE")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return None


def get_eur_per_usd() -> float:
    """Return EUR/USD exchange rate, cached for 1 hour.

    Falls back to EUR_USD_RATE env var, then 0.92 hardcoded default.
    Never raises; network errors are silently swallowed.
    """
    global _cached_rate, _cache_ts

    now = time.monotonic()
    if _cached_rate is not None and (now - _cache_ts) < _CACHE_TTL_S:
        return _cached_rate

    try:
        import requests  # local import keeps startup fast when requests absent

        resp = requests.get(_FRANKFURTER_URL, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        rate = float(data["rates"]["EUR"])
        _cached_rate = rate
        _cache_ts = now
        return rate
    except Exception:
        pass

    # Fallback chain: env var → hardcoded
    fallback = _env_fallback() or 0.92
    _cached_rate = fallback
    _cache_ts = now
    return fallback


def usd_to_eur(amount_usd: float) -> float:
    return amount_usd * get_eur_per_usd()


def clear_cache() -> None:
    """Reset the rate cache (useful in tests)."""
    global _cached_rate, _cache_ts
    _cached_rate = None
    _cache_ts = 0.0
