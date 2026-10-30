"""Base model: a regular Peewee model with Masonite conveniences."""
import datetime
import decimal
import json
import uuid

import inflection
import peewee
from peewee import ForeignKeyField, ModelBase, ModelSelect

from .collection import Collection
from .connections import get_proxy
from .expressions import build_conditions
from .pagination import LengthAwarePaginator, SimplePaginator, resolve_page

EVENTS = ("saving", "saved", "creating", "created", "updating", "updated", "deleting", "deleted")


class ModelNotFound(peewee.DoesNotExist):
    """Rendered by Masonite's exception handler as a 404."""

    is_http_exception = True

    def get_response(self):
        return str(self) or "Model Not Found"

    def get_status(self):
        return 404


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def _table_name(model_class):
    return inflection.tableize(model_class.__name__)


class ModelMeta(ModelBase):
    """Maps the masonite-orm style __table__ and __connection__ attributes onto
    Peewee's Meta options, unless Meta sets them explicitly."""

    def __new__(mcs, name, bases, attrs, **kwargs):
        overrides = {}
        if "__table__" in attrs:
            overrides["table_name"] = attrs["__table__"]
        if "__connection__" in attrs:
            overrides["database"] = get_proxy(attrs["__connection__"])
        if overrides:
            meta = attrs.get("Meta")
            options = {k: v for k, v in vars(meta).items() if not k.startswith("_")} if meta else {}
            attrs["Meta"] = type("Meta", (), {**overrides, **options})
        return super().__new__(mcs, name, bases, attrs, **kwargs)


class QuerySet(ModelSelect):
    """ModelSelect returned by Model.select(), with collection and pagination helpers."""

    def collect(self):
        return Collection(list(self))

    def paginator(self, per_page=15, page=None):
        page = resolve_page(page)
        total = self.count(clear_limit=True)
        items = Collection(list(self.paginate(page, per_page)))
        return LengthAwarePaginator(items, per_page, page, total)

    def simple_paginator(self, per_page=15, page=None):
        page = resolve_page(page)
        # fetch one extra row to know whether another page exists
        items = Collection(list(self.limit(per_page + 1).offset((page - 1) * per_page)))
        return SimplePaginator(items, per_page, page)

    def first_or_fail(self):
        instance = self.first()
        if instance is None:
            raise ModelNotFound("No record found for {}".format(self.model.__name__))
        return instance

    def update(self, values=None, **kwargs):
        """Update every row matched by this query."""
        model = self.model
        query = model.update(values, **kwargs)
        if self._where is not None:
            query = query.where(self._where)
        return query.execute()

    def delete(self):
        """Delete every row matched by this query."""
        query = self.model.delete()
        if self._where is not None:
            query = query.where(self._where)
        return query.execute()


class Model(peewee.Model, metaclass=ModelMeta):
    """Base model for Masonite applications.

    Fields, relationships and queries are plain Peewee. On top of that:
    __fillable__ / __guarded__   mass assignment rules for fill() and create()
    __hidden__ / __visible__     attributes left out of / kept in serialize()
    __appends__                  extra attributes (properties or methods) to serialize
    __timestamps__               maintain created_at / updated_at when those fields exist
    __table__ / __connection__   table name and connection (defaults: "users", "default")
    """

    __fillable__ = ["*"]
    __guarded__ = []
    __hidden__ = []
    __visible__ = []
    __appends__ = []
    __timestamps__ = True

    class Meta:
        database = get_proxy("default")
        table_function = _table_name

    @classmethod
    def select(cls, *fields):
        is_default = not fields
        if not fields:
            fields = cls._meta.sorted_fields
        return QuerySet(cls, fields, is_default=is_default)

    # masonite-orm compatible helpers used by Masonite's auth, guards and tests

    @classmethod
    def where(cls, column, *args):
        return cls.select().where(*build_conditions(cls._field, column, args))

    @classmethod
    def find(cls, key):
        primary_key = cls._meta.primary_key
        if isinstance(key, (list, tuple, set)):
            return cls.select().where(primary_key.in_(list(key))).collect()
        return cls.select().where(primary_key == key).first()

    @classmethod
    def find_or_fail(cls, key):
        instance = cls.find(key)
        if instance is None:
            raise ModelNotFound("No record found with the given primary key")
        return instance

    @classmethod
    def all(cls):
        return cls.select().collect()

    @classmethod
    def first(cls):
        return cls.select().first()

    @classmethod
    def create(cls, attributes=None, **kwargs):
        instance = cls()
        instance.fill({**(attributes or {}), **kwargs})
        instance.save(force_insert=True)
        return instance

    @classmethod
    def get_table_name(cls):
        return cls._meta.table_name

    @classmethod
    def get_primary_key(cls):
        return cls._meta.primary_key.column_name

    def get_primary_key_value(self):
        return self._pk

    @classmethod
    def _field(cls, name):
        try:
            return cls._meta.combined[name]
        except KeyError:
            raise AttributeError(
                "{} has no field or column named '{}'".format(cls.__name__, name)
            ) from None

    # mass assignment

    @classmethod
    def is_fillable(cls, name):
        if name in cls.__guarded__ or "*" in cls.__guarded__:
            return False
        return "*" in cls.__fillable__ or name in cls.__fillable__

    def fill(self, attributes):
        """Set the fillable attributes; unknown and guarded keys are ignored."""
        fields = self._meta.combined
        for key, value in attributes.items():
            if key in fields and self.is_fillable(key):
                setattr(self, fields[key].name, value)
        return self

    # persistence

    def save(self, force_insert=False, only=None):
        creating = force_insert or self._pk is None
        self._fire("saving")
        self._fire("creating" if creating else "updating")
        only = self._touch_timestamps(creating, only)
        result = super().save(force_insert=force_insert, only=only)
        self._fire("created" if creating else "updated")
        self._fire("saved")
        return result

    def delete_instance(self, *args, **kwargs):
        self._fire("deleting")
        result = super().delete_instance(*args, **kwargs)
        self._fire("deleted")
        return result

    def fresh(self):
        return type(self).find(self._pk)

    def _touch_timestamps(self, creating, only):
        if not self.__timestamps__:
            return only
        fields = self._meta.fields
        now = utcnow()
        touched = []
        if "updated_at" in fields:
            self.updated_at = now
            touched.append(fields["updated_at"])
        if creating and "created_at" in fields and self.created_at is None:
            self.created_at = now
            touched.append(fields["created_at"])
        if only:
            only = list(only) + touched
        return only

    # observers

    @classmethod
    def observe(cls, observer):
        if "_observers" not in cls.__dict__:
            cls._observers = []
        cls._observers.append(observer)

    def _fire(self, event):
        for observer in type(self).__dict__.get("_observers", []):
            handler = getattr(observer, event, None)
            if handler:
                handler(self)

    # serialization

    def set_appends(self, appends):
        self._extra_appends = list(appends)
        return self

    def serialize(self, include=None, exclude=None):
        data = {}
        for name, field in self._meta.fields.items():
            key = field.column_name if isinstance(field, ForeignKeyField) else name
            data[key] = _serialize_value(self.__data__.get(name))

        for name in self.__appends__ + getattr(self, "_extra_appends", []):
            value = getattr(self, name)
            data[name] = _serialize_value(value() if callable(value) else value)

        # relations that are already loaded (joined, prefetched or accessed)
        for name, related in self.__rel__.items():
            if isinstance(related, Model):
                data[name] = related.serialize()

        for name in include or []:
            data[name] = _serialize_value(getattr(self, name))

        if self.__visible__:
            data = {k: v for k, v in data.items() if k in self.__visible__}
        hidden = list(self.__hidden__) + list(exclude or [])
        return {k: v for k, v in data.items() if k not in hidden}

    def to_json(self, **kwargs):
        return json.dumps(self.serialize(**kwargs))

    def to_dict(self):
        return self.serialize()


def _serialize_value(value):
    if isinstance(value, Model):
        return value.serialize()
    if isinstance(value, (Collection, peewee.SelectBase, list, tuple)):
        return [_serialize_value(item) for item in value]
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (decimal.Decimal, uuid.UUID)):
        return str(value)
    return value


class SoftDeletes:
    """Mixin turning delete_instance() into an update of deleted_at.

    The model must declare the column, e.g. deleted_at = DateTimeField(null=True).
    Class level Model.delete() queries still delete rows."""

    __deleted_at__ = "deleted_at"

    @classmethod
    def select(cls, *fields):
        return super().select(*fields).where(cls._deleted_at_field().is_null())

    @classmethod
    def with_trashed(cls, *fields):
        return super().select(*fields)

    @classmethod
    def only_trashed(cls, *fields):
        return super().select(*fields).where(cls._deleted_at_field().is_null(False))

    @classmethod
    def get_deleted_at_column(cls):
        return cls._deleted_at_field().column_name

    @classmethod
    def _deleted_at_field(cls):
        return cls._meta.fields[cls.__deleted_at__]

    def delete_instance(self, force=False, **kwargs):
        if force:
            return super().delete_instance(**kwargs)
        self._fire("deleting")
        setattr(self, self.__deleted_at__, utcnow())
        result = peewee.Model.save(self, only=[self._deleted_at_field()])
        self._fire("deleted")
        return result

    def force_delete(self, **kwargs):
        return self.delete_instance(force=True, **kwargs)

    def restore(self):
        setattr(self, self.__deleted_at__, None)
        return self.save()

    @property
    def is_trashed(self):
        return getattr(self, self.__deleted_at__) is not None
