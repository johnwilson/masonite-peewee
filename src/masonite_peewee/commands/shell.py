"""db:shell and a tinker command that auto-loads Peewee models."""
import os
import shutil
import subprocess
import sys
import types

from masonite.commands import Command
from masonite.commands.TinkerCommand import TinkerCommand as BaseTinkerCommand

from ..connections import get_manager


class DbShellCommand(Command):
    """
    Open the database's interactive client (sqlite3, mysql or psql).

    db:shell
        {--c|connection=default : The connection to open}
        {--s|show : Only print the command}
    """

    def handle(self):
        manager = get_manager()
        name = manager.resolve_name(self.option("connection"))
        config = manager.get_connection_details()[name]
        command, env = client_command(config)
        if self.option("show"):
            self.line(" ".join(command))
            return
        if not shutil.which(command[0]):
            self.error("{} is not installed or not in PATH.".format(command[0]))
            return -1
        return subprocess.call(command, env={**os.environ, **env})


def client_command(config):
    """Return (argv, extra environment) for the connection's CLI client.
    Passwords go through the environment so they don't appear in argv."""
    driver = config.get("driver")
    if driver == "sqlite":
        return ["sqlite3", config.get("database")], {}
    if driver == "mysql":
        command = ["mysql", "-h", str(config.get("host", "127.0.0.1"))]
        if config.get("port"):
            command += ["-P", str(config["port"])]
        command += ["-u", str(config.get("user", "root")), config.get("database")]
        return command, {"MYSQL_PWD": str(config.get("password") or "")}
    if driver == "postgres":
        command = ["psql", "-h", str(config.get("host", "127.0.0.1"))]
        if config.get("port"):
            command += ["-p", str(config["port"])]
        command += ["-U", str(config.get("user", "postgres")), config.get("database")]
        return command, {"PGPASSWORD": str(config.get("password") or "")}
    raise ValueError("db:shell does not support the '{}' driver".format(driver))


class TinkerCommand(BaseTinkerCommand):
    """
    Run a python shell with the container and Peewee models pre-loaded.

    tinker
        {--i|ipython : Run a IPython shell}
        {--d|directory=? : Override the directory to auto-load models from}
    """

    def handle(self):
        # Masonite's tinker runs `from masoniteorm.models import Model` to find
        # models; serve ours for the duration of the command (this also works
        # when masonite-orm is not installed).
        from ..models import Model

        original = sys.modules.get("masoniteorm.models")
        sys.modules["masoniteorm.models"] = types.SimpleNamespace(Model=Model)
        try:
            return super().handle()
        finally:
            if original is None:
                del sys.modules["masoniteorm.models"]
            else:
                sys.modules["masoniteorm.models"] = original
