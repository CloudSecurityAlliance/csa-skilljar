"""The seam. `Backend` is the protocol; `PolicyBackend` wraps it; `V2Backend` is real.

Every method takes keyword-only arguments so `PolicyBackend` can wrap uniformly, and
returns the raw v2 JSON:API envelope - shaping belongs to the delivery layer, not here.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

Envelope = dict[str, Any]


@runtime_checkable
class Backend(Protocol):
    def list_courses(self, *, title: str | None = None, cursor: str | None = None,
                     page_size: int | None = None) -> Envelope: ...


class FakeBackend:
    """In-memory double. Powers the entire offline suite - no network, no credentials.

    Deliberately implements the *shape* of v2's cursor pagination, including the
    `has_more` / `next_cursor` pair, because code that only ever sees a single page
    is code that has never exercised paging.
    """

    def __init__(self, courses: list[dict[str, Any]] | None = None) -> None:
        self._courses = list(courses or [])

    def list_courses(self, *, title: str | None = None, cursor: str | None = None,
                     page_size: int | None = None) -> Envelope:
        rows = self._courses
        if title is not None:
            needle = title.lower()
            rows = [c for c in rows if needle in c.get("attributes", {}).get("title", "").lower()]
        start = int(cursor) if cursor else 0
        size = page_size or 25
        page = rows[start:start + size]
        nxt = start + size
        more = nxt < len(rows)
        return {"data": page, "meta": {"page_size": size},
                "links": {"self": "/v2/courses/", "next": None, "prev": None},
                "has_more": more, "next_cursor": str(nxt) if more else None}
