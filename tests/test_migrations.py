import textwrap

import peewee
import pytest

from masonite_peewee.migrations import Migrator
from masonite_peewee.schema import Schema
from masonite_peewee.seeds import seeder_location

CREATE_OWNERS = '''
from masonite_peewee.migrations import Migration


class CreateOwnersTable(Migration):
    def up(self):
        with self.schema.create("owners") as table:
            table.increments("id")

    def down(self):
        self.schema.drop("owners")
'''

CREATE_ITEMS = '''
from masonite_peewee.migrations import Migration


class CreateItemsTable(Migration):
    def up(self):
        with self.schema.create("items") as table:
            table.increments("id")
            table.string("name").unique()
            table.foreign_id("owner_id").constrained().on_delete("cascade")
            table.enum("kind", ["a", "b"]).default("a")
            table.timestamps()

    def down(self):
        self.schema.drop("items")
'''

ADD_PRICE = '''
from masonite_peewee.migrations import Migration


class AddPriceToItems(Migration):
    def up(self):
        with self.schema.table("items") as table:
            table.decimal("price", 8, 2).default(0)

    def down(self):
        with self.schema.table("items") as table:
            table.drop_column("price")
'''


@pytest.fixture
def migrations(tmp_path, db):
    (tmp_path / "2023_01_01_000000_create_owners_table.py").write_text(textwrap.dedent(CREATE_OWNERS))
    (tmp_path / "2024_01_01_000000_create_items_table.py").write_text(textwrap.dedent(CREATE_ITEMS))
    return tmp_path


def test_migrate_rollback_and_status(migrations, db):
    migrator = Migrator(str(migrations))
    schema = Schema(db.connection())
    assert [name for name, _ in migrator.migrate()] == [
        "2023_01_01_000000_create_owners_table",
        "2024_01_01_000000_create_items_table",
    ]
    assert schema.has_table("items")

    (migrations / "2024_01_02_000000_add_price_to_items.py").write_text(textwrap.dedent(ADD_PRICE))
    migrator.migrate()
    assert schema.has_column("items", "price")
    assert migrator.status() == [
        ("2023_01_01_000000_create_owners_table", 1),
        ("2024_01_01_000000_create_items_table", 1),
        ("2024_01_02_000000_add_price_to_items", 2),
    ]

    migrator.rollback()
    assert not schema.has_column("items", "price")
    assert migrator.pending() == ["2024_01_02_000000_add_price_to_items"]

    migrator.migrate()
    migrator.rollback(step=2)
    assert not schema.has_table("items") and schema.has_table("owners")
    migrator.rollback(step=1)
    assert migrator.ran() == []


def test_pretend_does_not_execute(migrations, db):
    migrator = Migrator(str(migrations))
    [_, (name, statements)] = migrator.migrate(pretend=True)
    assert any(s.startswith("CREATE TABLE") and "items" in s for s in statements)
    assert not Schema(db.connection()).has_table("items")
    assert migrator.ran() == []


def test_refresh_and_fresh(migrations, db):
    migrator = Migrator(str(migrations))
    migrator.migrate()
    db.connection().execute_sql("CREATE TABLE stray (id INTEGER)")
    migrator.refresh()
    assert {batch for _, batch in migrator.status()} == {1}
    migrator.fresh()
    assert "stray" not in db.connection().get_tables()
    assert Schema(db.connection()).has_table("items")


def test_failed_migration_is_rolled_back(tmp_path, db):
    (tmp_path / "2024_01_01_000000_broken.py").write_text(
        textwrap.dedent(
            '''
            from masonite_peewee.migrations import Migration


            class Broken(Migration):
                def up(self):
                    with self.schema.create("half") as table:
                        table.increments("id")
                    raise RuntimeError("boom")
            '''
        )
    )
    migrator = Migrator(str(tmp_path))
    with pytest.raises(RuntimeError):
        migrator.migrate()
    # MySQL commits DDL implicitly, so only the migration record is rolled back there
    if not isinstance(db.connection(), peewee.MySQLDatabase):
        assert not Schema(db.connection()).has_table("half")
    assert migrator.ran() == []


def test_seeder_location():
    assert seeder_location() == ("database_seeder", "DatabaseSeeder")
    assert seeder_location("User") == ("user_table_seeder", "UserTableSeeder")


def test_foreign_id_matches_referenced_key_type(migrations, db):
    Migrator(str(migrations)).migrate()
    types = {c.name: c.data_type.lower() for c in db.connection().get_columns("items")}
    assert "big" not in types["owner_id"]
