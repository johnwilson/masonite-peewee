from masonite.commands import Command

from ..seeds import run_seeder


class SeedRunCommand(Command):
    """
    Run a seeder: DatabaseSeeder by default, or e.g. "User" for UserTableSeeder.

    seed:run
        {name? : The seeder to run}
        {--c|connection=default : The connection to seed}
        {--d|directory=? : The seeds directory}
    """

    def __init__(self, directory="databases/seeds"):
        super().__init__()
        self.directory = directory

    def handle(self):
        seeder = run_seeder(
            self.option("directory") or self.directory,
            self.argument("name"),
            connection=self.option("connection"),
        )
        self.info("{} ran.".format(seeder.__name__))
