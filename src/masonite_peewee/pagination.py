"""Paginators serializing to the same shape as masonite-orm's."""
import json
import math


class BasePaginator:
    def __iter__(self):
        return iter(self.result)

    def __len__(self):
        return len(self.result)

    def to_json(self, *args, **kwargs):
        return json.dumps(self.serialize(*args, **kwargs))


class LengthAwarePaginator(BasePaginator):
    def __init__(self, result, per_page, current_page, total, url=None):
        self.result = result
        self.per_page = per_page
        self.current_page = current_page
        self.total = total
        self.url = url
        self.count = len(result)
        self.last_page = int(math.ceil(total / per_page)) if per_page else 0
        self.next_page = current_page + 1 if self.has_more_pages() else None
        self.previous_page = current_page - 1 or None

    def has_more_pages(self):
        return self.current_page < self.last_page

    def serialize(self, *args, **kwargs):
        return {
            "data": self.result.serialize(*args, **kwargs),
            "meta": {
                "total": self.total,
                "next_page": self.next_page,
                "count": self.count,
                "previous_page": self.previous_page,
                "last_page": self.last_page,
                "current_page": self.current_page,
            },
        }


class SimplePaginator(BasePaginator):
    """Paginator that skips the COUNT query. `result` must hold up to
    per_page + 1 items: the extra one only signals that another page exists."""

    def __init__(self, result, per_page, current_page, url=None):
        self._has_more = len(result) > per_page
        self.result = result.take(per_page) if self._has_more else result
        self.per_page = per_page
        self.current_page = current_page
        self.url = url
        self.count = len(self.result)
        self.next_page = current_page + 1 if self._has_more else None
        self.previous_page = current_page - 1 or None

    def has_more_pages(self):
        return self._has_more

    def serialize(self, *args, **kwargs):
        return {
            "data": self.result.serialize(*args, **kwargs),
            "meta": {
                "next_page": self.next_page,
                "count": self.count,
                "previous_page": self.previous_page,
                "current_page": self.current_page,
            },
        }


def _default_page_resolver():
    return 1


# The provider replaces this with one reading ?page= from the current request.
page_resolver = _default_page_resolver


def resolve_page(page=None):
    if page is None:
        page = page_resolver()
    try:
        return max(int(page), 1)
    except (TypeError, ValueError):
        return 1
