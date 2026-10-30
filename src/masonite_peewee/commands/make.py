"""make:migration, make:model, make:seed, make:observer and the table migration commands."""
import os

import inflection
from masonite.commands import Command
from masonite.utils.time import migration_timestamp

STUBS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "stubs")


def render(stub, **replacements):
    with open(os.path.join(STUBS, stub)) as fp:
        content = fp.read()
    for key, value in replacements.items():
        content = content.replace("__{}__".format(key), value)
    return content


def write(path, content):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fp:
        fp.write(content)


def make_migration(directory, name, create=None, table=None):
    if create:
        content = render("create_migration.stub", **{"class": inflection.camelize(name), "table": create})
    elif table:
        content = render("table_migration.stub", **{"class": inflection.camelize(name), "table": table})
    else:
        content = render("migration.stub", **{"class": inflection.camelize(name)})
    path = os.path.join(directory, "{}_{}.py".format(migration_timestamp(), name))
    write(path, content)
    return path


class MakeMigrationCommand(Command):
    """
    Create a migration file.

    make:migration
        {name : Name of the migration, e.g. create_posts_table}
        {--c|create=? : The table to create}
        {--t|table=? : The table to alter}
        {--d|directory=? : The migrations directory}
    """

    def __init__(self, directory="databases/migrations"):
        super().__init__()
        self.directory = directory

    def handle(self):
        path = make_migration(
            self.option("directory") or self.directory,
            inflection.underscore(self.argument("name")),
            create=self.option("create"),
            table=self.option("table"),
        )
        self.info("Migration file created: {}".format(path))


class MakeModelCommand(Command):
    """
    Create a model.

    make:model
        {name : Name of the model}
        {--m|migration : Also create a migration for the model's table}
        {--s|seeder : Also create a seeder}
        {--d|directory=? : The models directory}
        {--f|force : Overwrite the model if it exists}
    """

    def __init__(self, directory="app/models", migrations_directory="databases/migrations", seeds_directory="databases/seeds"):
        super().__init__()
        self.directory = directory
        self.migrations_directory = migrations_directory
        self.seeds_directory = seeds_directory

    def handle(self):
        name = inflection.camelize(self.argument("name"))
        path = os.path.join(self.option("directory") or self.directory, name + ".py")
        if os.path.exists(path) and not self.option("force"):
            self.warning("{} already exists! Use --force to overwrite it.".format(path))
            return -1
        write(path, render("model.stub", **{"class": name}))
        self.info("Model created: {}".format(path))

        if self.option("migration"):
            table = inflection.tableize(name)
            migration = make_migration(self.migrations_directory, "create_{}_table".format(table), create=table)
            self.info("Migration file created: {}".format(migration))

        if self.option("seeder"):
            seeder = make_seeder(self.seeds_directory, name)
            self.info("Seeder created: {}".format(seeder))


def make_seeder(directory, name):
    base = inflection.underscore(name)
    if not base.endswith("_seeder"):
        base += "_table_seeder"
    path = os.path.join(directory, base + ".py")
    write(path, render("seeder.stub", **{"class": inflection.camelize(base)}))
    return path


class MakeSeedCommand(Command):
    """
    Create a seeder.

    make:seed
        {name : Name of the seeder, e.g. User creates UserTableSeeder}
        {--d|directory=? : The seeds directory}
    """

    def __init__(self, directory="databases/seeds"):
        super().__init__()
        self.directory = directory

    def handle(self):
        path = make_seeder(self.option("directory") or self.directory, self.argument("name"))
        self.info("Seeder created: {}".format(path))


class MakeObserverCommand(Command):
    """
    Create a model observer.

    make:observer
        {name : Name of the observer}
        {--d|directory=? : The observers directory}
    """

    def __init__(self, directory="app/observers"):
        super().__init__()
        self.directory = directory

    def handle(self):
        name = inflection.camelize(self.argument("name"))
        if not name.endswith("Observer"):
            name += "Observer"
        path = os.path.join(self.option("directory") or self.directory, name + ".py")
        write(path, render("observer.stub", **{"class": name}))
        self.info("Observer created: {}".format(path))


class StubMigrationCommand(Command):
    """Writes a fixed migration stub, e.g. the jobs or notifications table."""

    stub = None
    migration_name = None

    def handle(self):
        path = os.path.join(
            self.option("directory"), "{}_{}.py".format(migration_timestamp(), self.migration_name)
        )
        write(path, render(self.stub))
        self.info("Migration file created: {}".format(path))


class QueueTableCommand(StubMigrationCommand):
    """
    Create the migration for the jobs table.

    queue:table
        {--d|directory=databases/migrations : The migrations directory}
    """

    stub = "create_queue_jobs_table.stub"
    migration_name = "create_queue_jobs_table"


class QueueFailedCommand(StubMigrationCommand):
    """
    Create the migration for the failed jobs table.

    queue:failed
        {--d|directory=databases/migrations : The migrations directory}
    """

    stub = "create_failed_jobs_table.stub"
    migration_name = "create_failed_jobs_table"


class NotificationTableCommand(StubMigrationCommand):
    """
    Create the migration for the notifications table.

    notification:table
        {--d|directory=databases/migrations : The migrations directory}
    """

    stub = "create_notifications_table.stub"
    migration_name = "create_notifications_table"
