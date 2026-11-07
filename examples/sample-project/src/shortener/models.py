from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Link:
    """A stored short link. Times are UTC seconds since the epoch."""

    code: str
    url: str
    created_at: float
    expires_at: Optional[float] = None  # None means the link never expires (slice 01)
