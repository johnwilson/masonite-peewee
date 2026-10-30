"""migrate, migrate:rollback, migrate:reset, migrate:refresh, migrate:fresh, migrate:status."""
import os

from masonite.commands import Command

from ..migrations import Migrator
from ..seeds import run_seeder


class MigratorCommand(Command):
    def __init__(self, directory="databases/migrations", seeds_directory="databases/seeds"):
        super().__init__()
        self.migrations_directory = directory
        self.seeds_directory = seeds_directory

    def get_migrator(self):
        return Migrator(
            directory=self.option("directory") or self.migrations_directory,
            connection=self.option("connection"),
        )

    def confirmed(self):
        if os.getenv("APP_ENV") != "production" or self.option("force"):
            return True
        return self.confirm("Application is in production. Do you really want to run this command?", False)

    def report(self, results, verb, show=False):
        if not results:
            self.info("Nothing to {}.".format(verb))
            return
        for name, statements in results:
            self.info("{}: {}".format(verb.capitalize(), name))
            if show:
                for statement in statements:
                    self.line("    " + statement)

    def seed(self):
        seeder = self.option("seed")
        if seeder:
            name = None if seeder is True else seeder
            run_seeder(self.seeds_directory, name, connection=self.option("connection"))
            self.info("Database seeded.")


class MigrateCommand(MigratorCommand):
    """
    Run pending migrations.

    migrate
        {--c|connection=default : The connection to run the migrations on}
        {--d|directory=? : The migrations directory}
        {--s|show : Show the SQL that would run without running it}
        {--seed=? : Seed the database afterwards, optionally with a given seeder}
        {--f|force : Run the migrations in production without asking}
    """

    def handle(self):
        if not self.confirmed():
            return
        show = self.option("show")
        self.report(self.get_migrator().migrate(pretend=show), "migrate", show=show)
        if not show:
            self.seed()


class MigrateRollbackCommand(MigratorCommand):
    """
    Roll back the last batch of migrations.

    migrate:rollback
        {--c|connection=default : The connection to run the migrations on}
        {--d|directory=? : The migrations directory}
        {--step=? : Roll back this number of migrations instead of the last batch}
        {--s|show : Show the SQL that would run without running it}
        {--f|force : Run in production without asking}
    """

    def handle(self):
        if not self.confirmed():
            return
        show = self.option("show")
        results = self.get_migrator().rollback(step=self.option("step"), pretend=show)
        self.report(results, "rollback", show=show)


class MigrateResetCommand(MigratorCommand):
    """
    Roll back every migration.

    migrate:reset
        {--c|connection=default : The connection to run the migrations on}
        {--d|directory=? : The migrations directory}
        {--s|show : Show the SQL that would run without running it}
        {--f|force : Run in production without asking}
    """

    def handle(self):
        if not self.confirmed():
            return
        show = self.option("show")
        self.report(self.get_migrator().reset(pretend=show), "rollback", show=show)


class MigrateRefreshCommand(MigratorCommand):
    """
    Roll back every migration, then migrate again.

    migrate:refresh
        {--c|connection=default : The connection to run the migrations on}
        {--d|directory=? : The migrations directory}
        {--seed=? : Seed the database afterwards, optionally with a given seeder}
        {--f|force : Run in production without asking}
    """

    def handle(self):
        if not self.confirmed():
            return
        migrator = self.get_migrator()
        self.report(migrator.reset(), "rollback")
        self.report(migrator.migrate(), "migrate")
        self.seed()


class MigrateFreshCommand(MigratorCommand):
    """
    Drop every table, then run all migrations.

    migrate:fresh
        {--c|connection=default : The connection to run the migrations on}
        {--d|directory=? : The migrations directory}
        {--seed=? : Seed the database afterwards, optionally with a given seeder}
        {--f|force : Run in production without asking}
    """

    def handle(self):
        if not self.confirmed():
            return
        self.report(self.get_migrator().fresh(), "migrate")
        self.seed()


class MigrateStatusCommand(MigratorCommand):
    """
    Show which migrations have run.

    migrate:status
        {--c|connection=default : The connection to inspect}
        {--d|directory=? : The migrations directory}
    """

    def handle(self):
        rows = [
            [name, "Yes" if batch is not None else "No", str(batch) if batch is not None else ""]
            for name, batch in self.get_migrator().status()
        ]
        if not rows:
            self.info("No migrations found.")
            return
        self.table(["Migration", "Ran?", "Batch"], rows).render()
