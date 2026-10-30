"""Test helpers. Masonite's own masonite.tests.DatabaseTransactions works
unchanged with DatabaseManager; RefreshDatabase also migrates first."""
from .migrations import Migrator

_migrated = set()


class RefreshDatabase:
    """Runs migrate:fresh once per test run and connection, then wraps every
    test in a transaction that is rolled back.

    Set `migrations_directory` on the test case to change the default."""

    migrations_directory = "databases/migrations"

    def startTestRun(self):
        resolver = self.application.make("resolver")
        connection = getattr(self, "connection", None)
        key = (resolver.resolve_name(connection), self.migrations_directory)
        if key not in _migrated:
            Migrator(self.migrations_directory, connection=connection or "default").fresh()
            _migrated.add(key)
        resolver.begin_transaction(connection)
        return self

    def stopTestRun(self):
        self.application.make("resolver").rollback(getattr(self, "connection", None))
        return self
