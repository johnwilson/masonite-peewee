"""Collections returned by model queries."""
from masonite.utils.collections import Collection as BaseCollection


class Collection(BaseCollection):
    """Masonite's Collection, holding Peewee model instances."""

    def serialize(self, *args, **kwargs):
        def _serialize(item):
            if self.__appends__ and hasattr(item, "set_appends"):
                item.set_appends(self.__appends__)
            if hasattr(item, "serialize"):
                return item.serialize(*args, **kwargs)
            if hasattr(item, "to_dict"):
                return item.to_dict()
            return item

        return list(map(_serialize, self))


def collect(iterable=None):
    return Collection(list(iterable or []))
