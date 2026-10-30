"""The masonite-peewee console script.

    masonite-peewee new my-app [--db=postgres ...]   craft a project wired for Peewee
    masonite-peewee install [path]                   convert an existing project
"""
import os
import sys

from cleo.application import Application
from masonite.commands import Command
from masonite.commands.NewCommand import NewCommand

from . import __version__
from .installer import SKIPPED, UPDATED, ProjectInstaller


def print_results(command, results, verbose=True):
    for status, relative, message in results:
        if status == SKIPPED:
            command.comment("  skipped  {}: {}".format(relative, message))
        elif verbose and status == UPDATED:
            command.line("  updated  {}: {}".format(relative, message))


class NewProjectCommand(NewCommand):
    """
    Creates a new Masonite project that uses Peewee as its ORM

    new
        {target? : Path of your Masonite project}
        {--api : Scaffold an API-ready project}
        {--preset= : Frontend preset to use (tailwind, bootstrap, vue, react, none)}
        {--db= : Database driver to configure (sqlite, mysql, postgres)}
        {--requirement= : requirements.txt line for masonite-peewee (defaults to the installed version)}
        {--no-venv : Do not create a virtual environment or install dependencies}
        {--no-git : Do not initialize a git repository}
        {--no-serve : Do not offer to start the development server}
        {--no-input : Do not ask any interactive question and use defaults}
        {--f|--force : Craft the project even if the target directory is not empty}
        {--repo= : Craft the project from a custom repository instead of the bundled skeleton}
        {--b|--branch=False : Specify which branch you would like to install when using --repo}
        {--r|--release=False : Specify which version you would like to install when using --repo}
        {--p|--provider=github : Repository provider to use with --repo (github, gitlab)}
    """

    # Masonite's wizard runs unchanged. The skeleton is converted right after
    # its requirements are written, so the venv step installs masonite-peewee.
    def _patch_requirements(self, to_dir, database):
        super()._patch_requirements(to_dir, database)
        self._install_peewee(to_dir)

    def _download_flow(self, target, to_dir):
        result = super()._download_flow(target, to_dir)
        if os.path.isfile(os.path.join(to_dir, "config", "database.py")):
            self._install_peewee(to_dir)
        return result

    def _install_peewee(self, to_dir):
        results = ProjectInstaller(to_dir, self.option("requirement")).run()
        self._done("Configured masonite-peewee as the ORM")
        print_results(self, results, verbose=False)


class InstallCommand(Command):
    """
    Switches an existing Masonite project from masonite-orm to masonite-peewee

    install
        {path? : Path of your Masonite project (defaults to the current directory)}
        {--requirement= : requirements.txt line for masonite-peewee (defaults to the installed version)}
    """

    def handle(self):
        installer = ProjectInstaller(self.argument("path") or ".", self.option("requirement"))
        if not installer.is_masonite_project():
            self.error("{} is not a Masonite project (craft, config/database.py and app/Kernel.py are required).".format(installer.root))
            return 1
        results = installer.run()
        print_results(self, results)
        if any(status == SKIPPED for status, _, _ in results):
            self.comment("Finish the skipped steps by hand; the README lists each manual change.")
        else:
            self.info("Done. Run `pip install -r requirements.txt` then `python craft migrate`.")
        return 0


application = Application("masonite-peewee", __version__)
application.add(NewProjectCommand())
application.add(InstallCommand())


def main():
    sys.exit(application.run())


if __name__ == "__main__":
    main()
