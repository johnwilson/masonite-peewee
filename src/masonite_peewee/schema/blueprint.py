"""Blueprint: the masonite-orm style table DSL used inside migrations."""
import inflection
import peewee
from peewee import SQL, Check


class Column:
    """A column being defined. Modifiers return the column so they can be chained."""

    def __init__(self, blueprint, name, field_class, **options):
        self.blueprint = blueprint
        self.name = name
        self.field_class = field_class
        self.options = {"null": False, **options}
        self.constraints = []
        self.has_default = False
        self.default_value = None
        self.is_change = False
        self.enum_values = None
        self.match_reference_type = False

    def nullable(self, value=True):
        self.options["null"] = value
        return self

    def default(self, value):
        self.has_default = True
        self.default_value = value
        self.options["default"] = value
        return self

    def use_current(self):
        self.constraints.append(SQL("DEFAULT CURRENT_TIMESTAMP"))
        return self

    def unique(self, value=True):
        self.options["unique"] = value
        return self

    def index(self, value=True):
        self.options["index"] = value
        return self

    def primary(self):
        self.options["primary_key"] = True
        return self

    def change(self):
        self.is_change = True
        return self

    # accepted for masonite-orm compatibility; they have no Peewee equivalent
    def unsigned(self):
        return self

    def comment(self, text):
        return self

    def after(self, column):
        return self

    # foreign keys declared from the column: table.foreign_id("user_id").constrained()
    def references(self, column):
        return self.blueprint.foreign(self.name).references(column)

    def constrained(self, table=None, column="id"):
        table = table or inflection.pluralize(self.name[: -len("_id")] if self.name.endswith("_id") else self.name)
        return self.blueprint.foreign(self.name).references(column).on(table)

    def build(self, database, named=True):
        options = dict(self.options)
        constraints = list(self.constraints)
        if self.enum_values:
            values = ", ".join(literal(value, database) for value in self.enum_values)
            constraints.append(Check("{} IN ({})".format(quote_name(database, self.name), values)))
        if self.has_default:
            constraints.append(SQL("DEFAULT " + literal(self.default_value, database)))
        if constraints:
            options["constraints"] = constraints
        if named:
            options["column_name"] = self.name
        return self.field_class(**options)


class ForeignKey:
    def __init__(self, column):
        self.column = column
        self.ref_column = "id"
        self.ref_table = None
        self.on_delete_action = None
        self.on_update_action = None

    def references(self, column):
        self.ref_column = column
        return self

    def on(self, table):
        self.ref_table = table
        return self

    def on_delete(self, action):
        self.on_delete_action = action.upper()
        return self

    def on_update(self, action):
        self.on_update_action = action.upper()
        return self

    def sql(self, quote):
        sql = "FOREIGN KEY ({}) REFERENCES {} ({})".format(
            quote(self.column), quote(self.ref_table), quote(self.ref_column)
        )
        if self.on_delete_action:
            sql += " ON DELETE " + self.on_delete_action
        if self.on_update_action:
            sql += " ON UPDATE " + self.on_update_action
        return sql


class JSONField(peewee.Field):
    field_type = "JSON"


class JSONBField(peewee.Field):
    field_type = "JSONB"


class Blueprint:
    def __init__(self, table, creating=False):
        self.table = table
        self.creating = creating
        self.columns = []
        self.foreign_keys = []
        self.indexes = []  # (columns, unique, name)
        self.primary_key = None
        self.dropped_columns = []
        self.renamed_columns = []
        self.dropped_indexes = []
        self.dropped_foreign_keys = []

    def add_column(self, name, field_class, **options):
        column = Column(self, name, field_class, **options)
        self.columns.append(column)
        return column

    # column types

    def increments(self, name="id"):
        return self.add_column(name, peewee.AutoField)

    tiny_increments = increments

    def big_increments(self, name="id"):
        return self.add_column(name, peewee.BigAutoField)

    id = big_increments

    def uuid(self, name):
        return self.add_column(name, peewee.UUIDField)

    def string(self, name, length=255):
        return self.add_column(name, peewee.CharField, max_length=length)

    def char(self, name, length=255):
        return self.add_column(name, peewee.FixedCharField, max_length=length)

    def text(self, name):
        return self.add_column(name, peewee.TextField)

    tiny_text = medium_text = long_text = text

    def integer(self, name, length=None):
        return self.add_column(name, peewee.IntegerField)

    unsigned_integer = integer

    def big_integer(self, name, length=None):
        return self.add_column(name, peewee.BigIntegerField)

    unsigned_big_integer = big_integer

    def small_integer(self, name, length=None):
        return self.add_column(name, peewee.SmallIntegerField)

    tiny_integer = small_integer

    def foreign_id(self, name):
        column = self.add_column(name, peewee.BigIntegerField)
        # the integer type is matched to the referenced key when the table is
        # created, as MySQL rejects BIGINT -> INT foreign keys
        column.match_reference_type = True
        return column

    def boolean(self, name):
        return self.add_column(name, peewee.BooleanField)

    def decimal(self, name, length=17, precision=6):
        return self.add_column(name, peewee.DecimalField, max_digits=length, decimal_places=precision)

    def float(self, name):
        return self.add_column(name, peewee.FloatField)

    def double(self, name):
        return self.add_column(name, peewee.DoubleField)

    def json(self, name):
        return self.add_column(name, JSONField)

    def jsonb(self, name):
        return self.add_column(name, JSONBField)

    def enum(self, name, options):
        column = self.add_column(name, peewee.CharField, max_length=max(len(str(o)) for o in options))
        column.enum_values = list(options)
        return column

    def date(self, name):
        return self.add_column(name, peewee.DateField)

    def datetime(self, name, now=False):
        column = self.add_column(name, peewee.DateTimeField)
        return column.use_current() if now else column

    timestamp = datetime

    def time(self, name):
        return self.add_column(name, peewee.TimeField)

    def binary(self, name):
        return self.add_column(name, peewee.BlobField)

    def timestamps(self):
        self.timestamp("created_at").nullable().use_current()
        self.timestamp("updated_at").nullable().use_current()

    def soft_deletes(self, name="deleted_at"):
        return self.timestamp(name).nullable()

    def remember_token(self):
        return self.string("remember_token", 100).nullable()

    def morphs(self, name):
        self.integer("{}_id".format(name))
        self.string("{}_type".format(name))
        self.index(["{}_id".format(name), "{}_type".format(name)])

    # table level constraints

    def primary(self, columns, name=None):
        self.primary_key = [columns] if isinstance(columns, str) else list(columns)

    def index(self, columns, name=None):
        self.indexes.append((_as_list(columns), False, name))

    def unique(self, columns, name=None):
        self.indexes.append((_as_list(columns), True, name))

    def foreign(self, column):
        foreign_key = ForeignKey(column)
        self.foreign_keys.append(foreign_key)
        return foreign_key

    # alterations

    def drop_column(self, *names):
        self.dropped_columns += names

    def rename(self, old, new):
        self.renamed_columns.append((old, new))

    rename_column = rename

    def drop_index(self, name):
        self.dropped_indexes.append(name)

    drop_unique = drop_index

    def drop_foreign(self, name):
        self.dropped_foreign_keys.append(name)

    def drop_timestamps(self):
        self.drop_column("created_at", "updated_at")

    def drop_soft_deletes(self, name="deleted_at"):
        self.drop_column(name)


def _as_list(columns):
    return [columns] if isinstance(columns, str) else list(columns)


def quote_name(database, name):
    return "{1}{0}{2}".format(name, *database.quote)


def literal(value, database):
    """Render a value as an SQL literal for a DEFAULT clause."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        if isinstance(database, peewee.PostgresqlDatabase):
            return "TRUE" if value else "FALSE"
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    return "'{}'".format(str(value).replace("'", "''"))
