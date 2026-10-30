"""Every test using the `db` fixture runs once per backend listed in
TEST_DATABASES (default: sqlite). Start MySQL and Postgres with
`docker compose up -d --wait`, then run TEST_DATABASES=sqlite,mysql,postgres pytest."""
import os

import pytest
from peewee import CharField, DateTimeField, ForeignKeyField

from masonite_peewee import DatabaseManager, Model, SoftDeletes
from masonite_peewee.migrations import Migrator

BACKENDS = {
    "sqlite": {"driver": "sqlite", "database": ":memory:"},
    "mysql": {
        "driver": "mysql",
        "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": os.getenv("MYSQL_PORT", "3307"),
        "database": "masonite_peewee",
        "user": "masonite",
        "password": "secret",
        "options": {"charset": "utf8mb4"},
    },
    "postgres": {
        "driver": "postgres",
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": os.getenv("POSTGRES_PORT", "5433"),
        "database": "masonite_peewee",
        "user": "masonite",
        "password": "secret",
    },
}
SELECTED = [name.strip() for name in os.getenv("TEST_DATABASES", "sqlite").split(",") if name.strip()]

manager = DatabaseManager({"default": SELECTED[0], **{name: BACKENDS[name] for name in SELECTED}})


class User(Model):
    __fillable__ = ["name", "email", "password"]
    __hidden__ = ["password"]

    name = CharField()
    email = CharField(unique=True)
    password = CharField(null=True)
    created_at = DateTimeField(null=True)
    updated_at = DateTimeField(null=True)


class Post(SoftDeletes, Model):
    user = ForeignKeyField(User, backref="posts")
    title = CharField()
    deleted_at = DateTimeField(null=True)


@pytest.fixture(params=SELECTED)
def db(request):
    manager._connection_details["default"] = request.param
    database = manager.connection()
    Migrator(connection=request.param).drop_all_tables()
    database.create_tables([User, Post])
    yield manager
    Migrator(connection=request.param).drop_all_tables()
    manager.close_all()
