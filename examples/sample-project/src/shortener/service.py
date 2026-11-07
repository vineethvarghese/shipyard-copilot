import time
from typing import Callable, Optional
from urllib.parse import urlparse

from .models import Link
from .store import InMemoryStore

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
MAX_TTL_SECONDS = 365 * 24 * 3600  # one year (C-4: no config change in this project)


class InvalidURL(ValueError):
    pass


class InvalidTTL(ValueError):
    pass


class UnknownCode(KeyError):
    pass


def _encode(n: int) -> str:
    out = ""
    while True:
        n, r = divmod(n, len(ALPHABET))
        out = ALPHABET[r] + out
        if n == 0:
            return out


class Shortener:
    def __init__(self, store: Optional[InMemoryStore] = None, clock: Callable[[], float] = time.time) -> None:
        self._store = store if store is not None else InMemoryStore()
        self._clock = clock
        self._next = 1

    def create(self, url: str, ttl_seconds: Optional[int] = None) -> Link:
        """Store `url` and return its Link. `ttl_seconds=None` means it never expires."""
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise InvalidURL(url)
        if ttl_seconds is not None:
            if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
                raise InvalidTTL("ttl_seconds must be an integer number of seconds")
            if not 0 < ttl_seconds <= MAX_TTL_SECONDS:
                raise InvalidTTL("ttl_seconds must be between 1 and %d" % MAX_TTL_SECONDS)
        now = self._clock()
        link = Link(code=_encode(self._next), url=url, created_at=now,
                    expires_at=None if ttl_seconds is None else now + ttl_seconds)
        self._next += 1
        self._store.put(link)
        return link

    def resolve(self, code: str) -> str:
        """Return the URL for `code`. Expiry is not enforced yet (slice 02)."""
        link = self._store.get(code)
        if link is None:
            raise UnknownCode(code)
        return link.url
