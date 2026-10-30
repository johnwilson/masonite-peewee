"""Runs migration files and records them in the "migrations" table.

The table layout (migration_id, migration, batch) is the one masonite-orm uses,
so an existing application keeps its migration history."""
import importlib.util
import inspect
import os
from contextlib import contextmanager

import peewee

from ..connections import get_manager
from ..schema import Schema
from .migration import Migration

READ_PREFIXES = ("select", "pragma", "show", "with", "explain")


class _NullCursor:
    rowcount = 0
    lastrowid = None
    description = ()

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __iter__(self):
        return iter([])


class Migrator:
    def __init__(self, directory="databases/migrations", connection="default", manager=None):
        self.directory = directory
        self.connection = connection
        self.manager = manager or get_manager()
        self.database = self.manager.connection(connection)
        self.schema = Schema(self.database)
        self.record = self._record_model()

    def _record_model(self):
        class MigrationRecord(peewee.Model):
            migration_id = peewee.AutoField()
            migration = peewee.CharField()
            batch = peewee.IntegerField()

            class Meta:
                database = self.database
                table_name = "migrations"

        return MigrationRecord

    def create_table(self):
        self.record.create_table(safe=True)

    # discovery

    def files(self):
        if not os.path.isdir(self.directory):
            return []
        return sorted(
            name[:-3]
            for name in os.listdir(self.directory)
            if name.endswith(".py") and not name.startswith("__")
        )

    def ran(self):
        self.create_table()
        return [r.migration for r in self.record.select().order_by(self.record.migration_id)]

    def pending(self):
        ran = set(self.ran())
        return [name for name in self.files() if name not in ran]

    def last_batch(self):
        self.create_table()
        return self.record.select(peewee.fn.MAX(self.record.batch)).scalar() or 0

    def status(self):
        """Return (migration, batch or None) for every known migration."""
        self.create_table()
        batches = {r.migration: r.batch for r in self.record.select()}
        names = sorted(set(self.files()) | set(batches))
        return [(name, batches.get(name)) for name in names]

    def load(self, name):
        path = os.path.join(self.directory, name + ".py")
        spec = importlib.util.spec_from_file_location("migrations." + name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for _, value in inspect.getmembers(module, inspect.isclass):
            if issubclass(value, Migration) and value.__module__ == module.__name__:
                return value
        raise ValueError("No Migration class found in {}".format(path))

    def instantiate(self, name):
        migration_class = self.load(name)
        if migration_class.connection != "default":
            return migration_class()
        return migration_class(connection=self.connection, schema=self.schema)

    # commands

    def migrate(self, pretend=False):
        """Run pending migrations. Returns [(name, statements)]."""
        pending = self.pending()
        batch = self.last_batch() + 1
        results = []
        for name in pending:
            statements = self._run(name, "up", pretend)
            if not pretend:
                self.record.create(migration=name, batch=batch)
            results.append((name, statements))
        return results

    def rollback(self, step=None, pretend=False):
        """Roll back the last batch, or the last `step` migrations."""
        self.create_table()
        query = self.record.select().order_by(self.record.migration_id.desc())
        if step:
            records = list(query.limit(int(step)))
        else:
            records = list(query.where(self.record.batch == self.last_batch()))
        return self._roll_back(records, pretend)

    def reset(self, pretend=False):
        self.create_table()
        records = list(self.record.select().order_by(self.record.migration_id.desc()))
        return self._roll_back(records, pretend)

    def refresh(self):
        return self.reset() + self.migrate()

    def fresh(self):
        """Drop every table, then run all migrations."""
        self.drop_all_tables()
        return self.migrate()

    def drop_all_tables(self):
        tables = self.database.get_tables()
        if isinstance(self.database, peewee.SqliteDatabase):
            self.database.execute_sql("PRAGMA foreign_keys = OFF")
            try:
                for table in tables:
                    self.schema.drop(table)
            finally:
                self.database.execute_sql("PRAGMA foreign_keys = ON")
        elif isinstance(self.database, peewee.MySQLDatabase):
            self.database.execute_sql("SET FOREIGN_KEY_CHECKS = 0")
            try:
                for table in tables:
                    self.schema.drop(table)
            finally:
                self.database.execute_sql("SET FOREIGN_KEY_CHECKS = 1")
        else:
            for table in tables:
                self.database.execute_sql("DROP TABLE IF EXISTS {} CASCADE".format(self.schema._quote(table)))

    def _roll_back(self, records, pretend):
        files = set(self.files())
        results = []
        for record in records:
            if record.migration not in files:
                raise FileNotFoundError(
                    "Migration file {}.py not found in {}".format(record.migration, self.directory)
                )
            statements = self._run(record.migration, "down", pretend)
            if not pretend:
                record.delete_instance()
            results.append((record.migration, statements))
        return results

    def _run(self, name, direction, pretend):
        migration = self.instantiate(name)
        database = migration.schema.database
        with self.capture(database, execute=not pretend) as statements:
            if pretend:
                getattr(migration, direction)()
            else:
                with database.atomic():
                    getattr(migration, direction)()
        return statements

    @contextmanager
    def capture(self, database, execute=True):
        """Record the SQL sent to the database. With execute=False only reads run."""
        statements = []
        original = database.execute_sql

        def execute_sql(sql, params=None, *args, **kwargs):
            if sql.lstrip().lower().startswith(READ_PREFIXES):
                return original(sql, params, *args, **kwargs)
            statements.append(_interpolate(sql, params))
            if execute:
                return original(sql, params, *args, **kwargs)
            return _NullCursor()

        database.execute_sql = execute_sql
        try:
            yield statements
        finally:
            del database.execute_sql


def _interpolate(sql, params):
    if not params:
        return sql
    return "{} -- {}".format(sql, list(params))
