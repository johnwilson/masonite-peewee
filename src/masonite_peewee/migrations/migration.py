from ..connections import get_manager
from ..schema import Schema


class Migration:
    """Base class for migration files. Override up() and down()."""

    connection = "default"

    def __init__(self, connection=None, schema=None):
        if connection:
            self.connection = connection
        self.schema = schema or Schema(get_manager().connection(self.connection))

    def up(self):
        pass

    def down(self):
        pass
