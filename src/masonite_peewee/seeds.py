"""Database seeders."""
import importlib
import os
import sys

import inflection


class Seeder:
    """Base class for seeders. Override run(); call() runs other seeders."""

    def __init__(self, connection="default"):
        self.connection = connection

    def run(self):
        raise NotImplementedError("Seeders must implement run()")

    def call(self, *seeders):
        for seeder in seeders:
            seeder(connection=self.connection).run()


def seeder_location(name=None):
    """Return (module name, class name) of a seeder, masonite-orm style:
    no name -> database_seeder.DatabaseSeeder, "User" -> user_table_seeder.UserTableSeeder."""
    if not name:
        return "database_seeder", "DatabaseSeeder"
    base = inflection.underscore(name)
    if not base.endswith("_seeder"):
        base += "_table_seeder"
    return base, inflection.camelize(base)


def load_seeder(directory, name=None):
    module_name, class_name = seeder_location(name)
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())
    package = directory.strip("/").replace("/", ".").replace(os.sep, ".")
    module = importlib.import_module("{}.{}".format(package, module_name))
    return getattr(module, class_name)


def run_seeder(directory, name=None, connection="default"):
    seeder_class = load_seeder(directory, name)
    seeder_class(connection=connection).run()
    return seeder_class
