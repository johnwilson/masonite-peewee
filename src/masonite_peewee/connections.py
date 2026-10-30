"""Connection management: turns Masonite's DATABASES dict into Peewee databases."""
from peewee import DatabaseProxy, MySQLDatabase, PostgresqlDatabase, SqliteDatabase
from playhouse.pool import (
    PooledMySQLDatabase,
    PooledPostgresqlDatabase,
    PooledSqliteDatabase,
)

DRIVERS = {
    "sqlite": (SqliteDatabase, PooledSqliteDatabase),
    "mysql": (MySQLDatabase, PooledMySQLDatabase),
    "postgres": (PostgresqlDatabase, PooledPostgresqlDatabase),
}

# Proxies are module level so models can be declared before the configuration
# is loaded; DatabaseManager initializes them once the connections are known.
_proxies = {}
_manager = None


def get_proxy(name="default"):
    if name not in _proxies:
        _proxies[name] = DatabaseProxy()
    return _proxies[name]


def get_manager():
    if _manager is None:
        raise RuntimeError(
            "No DatabaseManager configured. Define DB = DatabaseManager(DATABASES) "
            "in config/database.py."
        )
    return _manager


def build_database(config):
    """Create a Peewee database from a Masonite style connection dictionary."""
    if config.get("url"):
        from playhouse.db_url import connect

        return connect(config["url"])

    driver = config.get("driver")
    if driver not in DRIVERS:
        raise ValueError(
            "Unsupported database driver '{}'. Supported drivers: {}".format(
                driver, ", ".join(DRIVERS)
            )
        )
    plain_class, pooled_class = DRIVERS[driver]
    pool = config.get("pool")
    database_class = pooled_class if pool else plain_class
    kwargs = dict(pool) if isinstance(pool, dict) else {}

    if driver == "sqlite":
        kwargs.setdefault("pragmas", config.get("pragmas", {"foreign_keys": 1}))
        return database_class(config.get("database"), **kwargs)

    for key in ("host", "user", "password"):
        if config.get(key) not in (None, ""):
            kwargs[key] = config[key]
    if config.get("port"):
        kwargs["port"] = int(config["port"])
    kwargs.update(config.get("options") or {})
    return database_class(config.get("database"), **kwargs)


def _close_if_idle(database):
    # a connection inside a transaction (e.g. a test wrapped in
    # DatabaseTransactions) must stay open
    if not database.is_closed() and not database.in_transaction():
        database.close()


class _Rollback(Exception):
    pass


class _ConnectionDetails(dict):
    """Re-points the "default" proxy when the default connection name changes,
    as Masonite's TestCase does with resolver._connection_details["default"]."""

    def __init__(self, manager, *args):
        super().__init__(*args)
        self._manager = manager

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if key == "default" and value in self._manager._databases:
            get_proxy("default").initialize(self._manager._databases[value])


class DatabaseManager:
    """Holds every configured connection.

    Bound in the container as "resolver" and exposed as config("database.db"),
    so it also implements the ConnectionResolver methods Masonite calls."""

    def __init__(self, connection_details=None):
        global _manager
        self._connection_details = {}
        self._databases = {}
        self._transactions = {}
        _manager = self
        if connection_details:
            self.set_connection_details(connection_details)

    def set_connection_details(self, connection_details):
        self._databases = {}
        self._connection_details = _ConnectionDetails(self, connection_details)
        for name, config in connection_details.items():
            if isinstance(config, dict):
                self._databases[name] = build_database(config)
                get_proxy(name).initialize(self._databases[name])
        get_proxy("default").initialize(self.connection("default"))
        return self

    def get_connection_details(self):
        return self._connection_details

    def resolve_name(self, name=None):
        if name in (None, "default"):
            # TestCase rewrites _connection_details["default"] to switch connection
            return self._connection_details.get("default")
        return name

    def connection(self, name=None):
        resolved = self.resolve_name(name)
        if resolved not in self._databases:
            raise ValueError("Database connection '{}' is not configured.".format(name))
        return self._databases[resolved]

    def proxy(self, name="default"):
        return get_proxy(name)

    def get_query_builder(self, connection=None):
        from .query import TableQuery

        return TableQuery(self, connection=connection)

    def get_schema_builder(self, connection=None):
        from .schema import Schema

        return Schema(self.connection(connection))

    def connect(self, name=None, reuse_if_open=True):
        return self.connection(name).connect(reuse_if_open=reuse_if_open)

    def close(self, name=None):
        _close_if_idle(self.connection(name))

    def close_all(self):
        for database in self._databases.values():
            _close_if_idle(database)

    def transaction(self, connection=None):
        """Context manager / decorator wrapping a block in a transaction."""
        return self.connection(connection).atomic()

    def begin_transaction(self, connection=None):
        context = self.connection(connection).atomic()
        context.__enter__()
        self._transactions.setdefault(self.resolve_name(connection), []).append(context)
        return context

    def commit(self, connection=None):
        self._pop_transaction(connection).__exit__(None, None, None)

    def rollback(self, connection=None):
        # exiting an atomic block with an exception rolls back the transaction
        # (or the savepoint when nested)
        self._pop_transaction(connection).__exit__(_Rollback, _Rollback(), None)

    def _pop_transaction(self, connection):
        stack = self._transactions.get(self.resolve_name(connection))
        if not stack:
            raise RuntimeError("No open transaction on connection '{}'.".format(connection))
        return stack.pop()
