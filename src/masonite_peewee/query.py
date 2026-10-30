"""A small table query builder, bound in the container as "builder".

Masonite's internals (password resets, the database queue and notification
drivers, validation rules and TestCase assertions) talk to the database through
this masonite-orm style fluent API and read rows as dictionaries. It is not meant
for application code: use Peewee queries there.

Like masonite-orm's QueryBuilder it is mutable: clauses accumulate on the
instance and are cleared once a query is executed, while the table and the
connection are kept."""
from peewee import SQL, PostgresqlDatabase, Table

from .connections import get_manager
from .expressions import build_conditions


class TableQuery:
    def __init__(self, manager=None, connection=None, table=None):
        self._manager = manager
        self._connection = connection
        self.table(table)
        self._reset()

    def _reset(self):
        self._columns = []
        self._wheres = []
        self._orders = []
        self._limit = None
        self._offset = None

    @property
    def manager(self):
        return self._manager or get_manager()

    def new(self):
        return TableQuery(self._manager, self._connection, self._table)

    def on(self, connection):
        self._connection = connection
        return self

    def table(self, table):
        self._table = table
        # one Table object per query so column references share its alias
        self._peewee = Table(table) if table else None
        return self

    def select(self, *columns):
        self._columns += columns
        return self

    # Clauses are stored as callables and built at execution time: Masonite
    # sometimes calls where() before table(), e.g. builder.where(...).table(...)

    def where(self, column, *args):
        self._wheres.append(lambda: build_conditions(self._column, column, args))
        return self

    def where_in(self, column, values):
        values = list(values)
        self._wheres.append(lambda: [self._column(column).in_(values)])
        return self

    def where_not_in(self, column, values):
        values = list(values)
        self._wheres.append(lambda: [self._column(column).not_in(values)])
        return self

    def where_null(self, column):
        self._wheres.append(lambda: [self._column(column).is_null()])
        return self

    def where_not_null(self, column):
        self._wheres.append(lambda: [self._column(column).is_null(False)])
        return self

    def order_by(self, column, direction="ASC"):
        descending = direction.upper() == "DESC"
        self._orders.append(
            lambda: self._column(column).desc() if descending else self._column(column).asc()
        )
        return self

    def limit(self, amount):
        self._limit = amount
        return self

    take = limit

    def offset(self, amount):
        self._offset = amount
        return self

    skip = offset

    def get(self):
        query = self._peewee_table().select(*[self._column(c) for c in self._columns])
        query = self._apply_wheres(query)
        if self._orders:
            query = query.order_by(*[order() for order in self._orders])
        if self._limit is not None:
            query = query.limit(self._limit)
        if self._offset is not None:
            query = query.offset(self._offset)
        try:
            return list(query.dicts())
        finally:
            self._reset()

    all = get

    def first(self):
        self._limit = 1
        rows = self.get()
        return rows[0] if rows else None

    def count(self):
        query = self._apply_wheres(self._peewee_table().select())
        try:
            return query.count()
        finally:
            self._reset()

    def exists(self):
        return self.count() > 0

    def create(self, values):
        table = self._peewee_table()
        query = table.insert(self._values(values))
        try:
            if isinstance(table._database, PostgresqlDatabase):
                # an unbound table has no primary key for Peewee to return,
                # so ask Postgres for the whole inserted row
                return list(query.returning(SQL("*")).dicts().execute())[0]
            row_id = query.execute()
        finally:
            self._reset()
        record = dict(values)
        if row_id is not None and "id" not in record:
            record["id"] = row_id
        return record

    def update(self, values):
        query = self._apply_wheres(self._peewee_table().update(self._values(values)))
        try:
            return query.execute()
        finally:
            self._reset()

    def delete(self):
        query = self._apply_wheres(self._peewee_table().delete())
        try:
            return query.execute()
        finally:
            self._reset()

    def truncate(self):
        self._wheres = []
        return self.delete()

    def _peewee_table(self):
        if not self._table:
            raise ValueError("No table set on the query builder. Call table() first.")
        return self._peewee.bind(self.manager.connection(self._connection))

    def _column(self, name):
        return getattr(self._peewee.c, name)

    def _values(self, values):
        return {self._column(key): value for key, value in values.items()}

    def _apply_wheres(self, query):
        for build in self._wheres:
            for condition in build():
                query = query.where(condition)
        return query
