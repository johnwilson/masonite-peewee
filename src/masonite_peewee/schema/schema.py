"""Schema builder executing Blueprints through Peewee and playhouse.migrate."""
from contextlib import contextmanager

import peewee
from peewee import SQL, CompositeKey
from playhouse.migrate import SchemaMigrator, migrate

from .blueprint import Blueprint, quote_name


class Schema:
    def __init__(self, database):
        if isinstance(database, peewee.DatabaseProxy):
            database = database.obj
        self.database = database

    @property
    def migrator(self):
        return SchemaMigrator.from_database(self.database)

    @contextmanager
    def create(self, table):
        blueprint = Blueprint(table, creating=True)
        yield blueprint
        self._create_table(blueprint, safe=False)

    @contextmanager
    def create_table_if_not_exists(self, table):
        blueprint = Blueprint(table, creating=True)
        yield blueprint
        self._create_table(blueprint, safe=True)

    @contextmanager
    def table(self, table):
        blueprint = Blueprint(table)
        yield blueprint
        self._alter_table(blueprint)

    def drop(self, table):
        self.database.execute_sql("DROP TABLE {}".format(self._quote(table)))

    drop_table = drop

    def drop_table_if_exists(self, table):
        self.database.execute_sql("DROP TABLE IF EXISTS {}".format(self._quote(table)))

    drop_if_exists = drop_table_if_exists

    def rename(self, old, new):
        migrate(self.migrator.rename_table(old, new))

    def truncate(self, table):
        self.database.execute_sql("DELETE FROM {}".format(self._quote(table)))

    def has_table(self, table):
        return self.database.table_exists(table)

    def has_column(self, table, column):
        return column in [c.name for c in self.database.get_columns(table)]

    def get_tables(self):
        return self.database.get_tables()

    def _quote(self, name):
        return quote_name(self.database, name)

    def _create_table(self, blueprint, safe):
        self._match_foreign_id_types(blueprint)
        attributes = {column.name: column.build(self.database) for column in blueprint.columns}
        meta = {
            "database": self.database,
            "table_name": blueprint.table,
            "indexes": [(tuple(columns), unique) for columns, unique, _ in blueprint.indexes],
            "constraints": [SQL(fk.sql(self._quote)) for fk in blueprint.foreign_keys],
        }
        if blueprint.primary_key:
            meta["primary_key"] = CompositeKey(*blueprint.primary_key)
        elif not any(field.primary_key for field in attributes.values()):
            meta["primary_key"] = False
        attributes["Meta"] = type("Meta", (), meta)
        model = type(_model_name(blueprint.table), (peewee.Model,), attributes)
        self.database.create_tables([model], safe=safe)

    def _match_foreign_id_types(self, blueprint):
        columns = {column.name: column for column in blueprint.columns}
        for foreign_key in blueprint.foreign_keys:
            column = columns.get(foreign_key.column)
            if not column or not column.match_reference_type:
                continue
            if foreign_key.ref_table == blueprint.table:
                referenced = columns.get(foreign_key.ref_column)
                is_big = referenced is not None and referenced.field_class in (
                    peewee.BigAutoField,
                    peewee.BigIntegerField,
                )
            elif self.has_table(foreign_key.ref_table):
                types = {c.name: c.data_type.lower() for c in self.database.get_columns(foreign_key.ref_table)}
                is_big = "big" in types.get(foreign_key.ref_column, "big")
            else:
                continue
            column.field_class = peewee.BigIntegerField if is_big else peewee.IntegerField

    def _alter_table(self, blueprint):
        migrator = self.migrator
        table = blueprint.table
        operations = []

        for old, new in blueprint.renamed_columns:
            operations.append(migrator.rename_column(table, old, new))

        for column in blueprint.columns:
            # SqliteMigrator renders the column name itself when changing a type
            field = column.build(self.database, named=not column.is_change)
            if column.is_change:
                operations.append(migrator.alter_column_type(table, column.name, field))
                if field.null:
                    operations.append(migrator.drop_not_null(table, column.name))
                else:
                    operations.append(migrator.add_not_null(table, column.name))
            else:
                operations.append(migrator.add_column(table, column.name, field))

        for columns, unique, name in blueprint.indexes:
            operations.append(migrator.add_index(table, columns, unique, name=name))

        for foreign_key in blueprint.foreign_keys:
            operations.append(
                migrator.add_foreign_key_constraint(
                    table,
                    foreign_key.column,
                    foreign_key.ref_table,
                    foreign_key.ref_column,
                    on_delete=foreign_key.on_delete_action,
                    on_update=foreign_key.on_update_action,
                )
            )

        for name in blueprint.dropped_foreign_keys:
            operations.append(migrator.drop_foreign_key_constraint(table, name))

        for name in blueprint.dropped_indexes:
            operations.append(migrator.drop_index(table, name))

        for name in blueprint.dropped_columns:
            operations.append(migrator.drop_column(table, name))

        migrate(*operations)


def _model_name(table):
    return "".join(part.capitalize() for part in table.split("_")) or "Table"
