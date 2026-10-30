from masonite.configuration import config
from masonite.providers import Provider
from masonite.utils.location import migrations_path, models_path

from . import pagination
from .collection import Collection
from .commands import (
    DbShellCommand,
    MakeMigrationCommand,
    MakeModelCommand,
    MakeObserverCommand,
    MakeSeedCommand,
    MigrateCommand,
    MigrateFreshCommand,
    MigrateRefreshCommand,
    MigrateResetCommand,
    MigrateRollbackCommand,
    MigrateStatusCommand,
    NotificationTableCommand,
    QueueFailedCommand,
    QueueTableCommand,
    SeedRunCommand,
    TinkerCommand,
)
from .connections import DatabaseManager
from .query import TableQuery


class PeeweeProvider(Provider):
    """Replaces ORMProvider in config/providers.py."""

    def register(self):
        manager = config("database.db")
        if not isinstance(manager, DatabaseManager):
            raise TypeError(
                "config/database.py must define DB = DatabaseManager(DATABASES) "
                "(from masonite_peewee import DatabaseManager) to use PeeweeProvider."
            )
        self.application.bind("resolver", manager)
        self.application.bind("builder", TableQuery(manager))
        for key, default in (
            ("migrations.location", "databases/migrations"),
            ("seeds.location", "databases/seeds"),
            ("observers.location", "app/observers"),
        ):
            if not self.application.has(key):
                self.application.bind(key, default)

        pagination.page_resolver = self._current_page
        self._register_commands()
        self._patch_notification_manager()

    def _current_page(self):
        try:
            return self.application.make("request").input("page", 1)
        except Exception:
            return 1

    def _register_commands(self):
        migrations_dir = migrations_path(absolute=False)
        seeds_dir = self.application.make("seeds.location")
        commands = [
            MigrateCommand(migrations_dir, seeds_dir),
            MigrateRollbackCommand(migrations_dir, seeds_dir),
            MigrateResetCommand(migrations_dir, seeds_dir),
            MigrateRefreshCommand(migrations_dir, seeds_dir),
            MigrateFreshCommand(migrations_dir, seeds_dir),
            MigrateStatusCommand(migrations_dir, seeds_dir),
            MakeMigrationCommand(migrations_dir),
            MakeModelCommand(models_path(absolute=False), migrations_dir, seeds_dir),
            MakeSeedCommand(seeds_dir),
            MakeObserverCommand(self.application.make("observers.location")),
            SeedRunCommand(seeds_dir),
            DbShellCommand(),
            # these replace Masonite's versions, which generate masonite-orm migrations
            # or load masonite-orm models
            TinkerCommand(),
            QueueTableCommand(),
            QueueFailedCommand(),
            NotificationTableCommand(),
        ]
        capsule = self.application.make("commands")
        for command in commands:
            # CommandCapsule.add() ignores names already registered, so replace them
            if command.name in capsule.command_name:
                capsule.commands = [c for c in capsule.commands if c.name != command.name]
                capsule.command_name.remove(command.name)
            capsule.add(command)

    def _patch_notification_manager(self):
        # NotificationManager only treats lists, tuples and masonite-orm
        # Collections as several notifiables
        from masonite.notification.NotificationManager import NotificationManager
        from peewee import SelectBase

        original = NotificationManager._format_notifiables
        if getattr(original, "_peewee", False):
            return

        def _format_notifiables(manager, notifiables):
            if isinstance(notifiables, (Collection, SelectBase)):
                return list(notifiables)
            return original(manager, notifiables)

        _format_notifiables._peewee = True
        NotificationManager._format_notifiables = _format_notifiables
