from typing import Dict, Optional

from .models import Link


class InMemoryStore:
    """Keeps links in a dict. Good enough for a toy; swap for a database later."""

    def __init__(self) -> None:
        self._links: Dict[str, Link] = {}

    def put(self, link: Link) -> None:
        self._links[link.code] = link

    def get(self, code: str) -> Optional[Link]:
        return self._links.get(code)

    def __len__(self) -> int:
        return len(self._links)
