# masonite-peewee

Use [Peewee](https://docs.peewee-orm.com) as the ORM of a Masonite 5 application, in place of masonite-orm.
Built against `masonite-framework` 5.x (the masonitedev line on PyPI).

Models are plain Peewee models. Masonite's features that rely on the ORM keep working:

- authentication and password resets
- the database queue driver
- database notifications
- the `exists_in_db` / `unique_in_db` validation rules
- `TestCase` database assertions and `DatabaseTransactions`
- returning models, collections and paginators from controllers
- the `craft` migration and seeding commands

## Installation

```bash
pip install masonite-peewee
```

The package installs a `masonite-peewee` command. There are three ways to set up a project:

| | Use it for | Command |
|---|---|---|
| A | A new project | `masonite-peewee new my-app` |
| B | An existing project | `masonite-peewee install [path]` |
| C | Full control, or a heavily customised project | the manual steps below |

### A. New project

```bash
masonite-peewee new my-app --db=postgres
cd my-app && source .venv/bin/activate
python craft migrate
```

`new` runs Masonite's own `project new` wizard, with the same questions and options (`--api`, `--preset`, `--db`, `--no-venv`, `--no-git`, `--no-input`, ...). Right after the skeleton is copied, before the virtual environment is created, it applies option B to the new project. The venv step then installs masonite-peewee together with the database driver.

`--requirement` sets the line written to `requirements.txt`. By default it pins the installed version. When masonite-peewee was installed from a local checkout, the default points back to that checkout (`-e /path/to/masonite-peewee`).

### B. Existing project

```bash
cd my-app
masonite-peewee install            # or: masonite-peewee install path/to/my-app
pip install -r requirements.txt
```

`install` makes every change in option C:
- It reports each file it updates.
- It is safe to run again: files that are already converted are left alone.
- When a file has been customised and the expected code isn't there, it skips that step and tells you which file to finish by hand. For example, a `User` model with extra methods is never overwritten, because its fields have to be declared by hand.
- Finally it lists any other file that still imports `masoniteorm`, such as your own models.

### C. Manual setup

Add `masonite-peewee` to `requirements.txt`, then make the changes below. For MySQL or Postgres, also install `pymysql` or `psycopg2-binary`.

### 1. `config/database.py`

Keep the `DATABASES` dict as it is, and replace the resolver:

```python
from masonite_peewee import DatabaseManager

DB = DatabaseManager(DATABASES)
```

Connections support sqlite, mysql and postgres. MSSQL is not supported.

Each connection also accepts these keys:
- `"pool": {"max_connections": 8, "stale_timeout": 300}`, which uses `playhouse.pool`
- `"url": "postgres://..."`
- `"pragmas"` (SQLite only)

### 2. `config/providers.py`

Replace `ORMProvider` with `PeeweeProvider`, keeping the same position in the list:

```python
from masonite_peewee.provider import PeeweeProvider
```

### 3. `app/Kernel.py`

- In `register_database()`, delete the `QueryBuilder` import, the `builder` binding and the `resolver` binding. The provider binds both now.
- Add the middleware that closes connections after each request:

```python
from masonite_peewee.middleware import DatabaseConnectionMiddleware

http_middleware = [DatabaseConnectionMiddleware, ...]
```

### 4. Models, migrations and seeders

- In migrations, change `from masoniteorm.migrations import Migration` to `from masonite_peewee.migrations import Migration`.
- In seeders, change `from masoniteorm.seeds import Seeder` to `from masonite_peewee.seeds import Seeder`.
- Migration and seeder bodies don't change.
- Declare model fields with Peewee:

```python
from peewee import CharField, DateTimeField
from masonite.authentication import Authenticates
from masonite_peewee import Model
from masonite_peewee.notifications import Notifiable


class User(Model, Authenticates, Notifiable):
    __fillable__ = ["name", "email", "password"]
    __hidden__ = ["password"]

    name = CharField()
    email = CharField(unique=True)
    password = CharField()
    remember_token = CharField(null=True)
    created_at = DateTimeField(null=True)
    updated_at = DateTimeField(null=True)
```

Masonite's own `Authenticates`, `AuthenticatesTokens` and `Authorizes` mixins work unchanged. Import `Notifiable` from `masonite_peewee.notifications`, because Masonite's version is built on masonite-orm relationships.

The stock notifications migration uses an integer `id`, but Masonite stores UUID strings there. Use `table.string("id", 36).primary()`, or regenerate the migration with `craft notification:table`.

### 5. `config/queue.py` and `config/notification.py`

The database drivers of the skeleton hard-code `"connection": "sqlite"`. Change both to `"connection": "default"`, so jobs and notifications use the same database as the rest of the app.

## Models

`masonite_peewee.Model` is a `peewee.Model`. Fields, relationships (`ForeignKeyField`, `backref`, `ManyToManyField`), joins and `prefetch()` all behave exactly as in Peewee.

It adds:

| Attribute / method | Behaviour |
|---|---|
| table name | Pluralized snake case of the class name (`User` becomes `users`). Override it with `__table__` or `Meta.table_name`. |
| `__connection__` | Name of a connection in `DATABASES`. Defaults to `"default"`. |
| `__fillable__` / `__guarded__` | Mass-assignment rules for `fill()` and `create(dict)`. Unknown keys are ignored. |
| `__hidden__` / `__visible__` / `__appends__` | Control what `serialize()` / `to_json()` output. |
| `__timestamps__` | Sets `created_at` / `updated_at` on `save()` when the model declares them. Values are naive UTC. |
| `serialize(include=[...], exclude=[...])` | Returns a dict. Foreign keys appear as their column (`user_id`), dates as ISO strings. Relations that are joined or prefetched, and those named in `include`, are nested. |
| `Model.where(col, [op], val)`, `find`, `find_or_fail`, `all`, `first`, `create` | masonite-orm style helpers. Masonite's auth calls them too. |
| `Model.observe(Observer())` | Observer methods: `saving/saved`, `creating/created`, `updating/updated`, `deleting/deleted`. |
| `SoftDeletes` mixin | `delete_instance()` sets `deleted_at`, and `select()` hides trashed rows. Also adds `with_trashed()`, `only_trashed()`, `restore()` and `force_delete()`. |

`Model.select()` returns a `QuerySet`, which is a Peewee `ModelSelect` with a few extra methods:

```python
User.select().where(User.active == True).collect()     # Collection
User.select().order_by(User.id).paginator(15)          # LengthAwarePaginator; page defaults to ?page=
User.select().simple_paginator(15, page=2)             # SimplePaginator, no COUNT query
User.select().where(...).update({"active": False})     # bulk update / delete of the matched rows
```

Peewee's own `.paginate(page, per_page)` and `.get()` keep their Peewee meaning.

## Collections and pagination

`Collection` is Masonite's `masonite.utils.collections.Collection`, holding model instances. The paginators serialize to the same shape as masonite-orm's, so API clients don't change:

```json
{"data": [...], "meta": {"total": 5, "next_page": 3, "count": 2, "previous_page": 1, "last_page": 3, "current_page": 2}}
```

A controller can return a model, a collection or a paginator directly, and Masonite renders it as JSON.

## Migrations

You write migrations in the masonite-orm schema DSL. They run through Peewee and `playhouse.migrate`.

```python
with self.schema.create("posts") as table:
    table.increments("id")
    table.string("title").unique()
    table.foreign_id("user_id").constrained().on_delete("cascade")
    table.enum("status", ["draft", "published"]).default("draft")
    table.json("meta").nullable()
    table.timestamps()

with self.schema.table("posts") as table:
    table.string("subtitle").nullable()
    table.string("title", 100).change()
    table.rename("body", "content")
    table.drop_column("legacy")
```

History is kept in the same `migrations` table as masonite-orm (`migration_id`, `migration`, `batch`), so an existing application keeps its history. Each migration runs in a transaction. On Postgres and SQLite, a failed migration leaves nothing behind. MySQL commits DDL implicitly, so there a failed migration is not recorded but any tables it already created remain.

`foreign_id("user_id").constrained()` creates the column with the same integer type as the referenced key. MySQL rejects a BIGINT column referencing an INT key, which is what `increments()` creates.

### Commands

| Command | Description |
|---|---|
| `migrate [--show] [--seed[=Name]]` | `--show` prints the SQL without running it. |
| `migrate:rollback [--step=N]` | |
| `migrate:reset` | |
| `migrate:refresh [--seed]` | |
| `migrate:fresh [--seed]` | |
| `migrate:status` | |
| `make:migration name [--create=table \| --table=table]` | |
| `make:model Name [-m] [-s]` | |
| `make:seed Name` | |
| `make:observer Name` | |
| `seed:run [Name]` | |
| `db:shell [--show]` | |
| `tinker` | Auto-loads Peewee models. |
| `queue:table`, `queue:failed`, `notification:table` | Generate masonite-peewee migrations. |

All of them accept `--connection`.

## Testing

`masonite.tests.DatabaseTransactions` works as is. `masonite_peewee.testing.RefreshDatabase` also runs `migrate:fresh` once per test run before wrapping each test in a transaction.

## Known limitations

- MSSQL is not supported.
- Adding or dropping a foreign key on an existing table is not supported on SQLite: Peewee's SQLite migrator cannot do it. Declare foreign keys in `schema.create(...)` instead.
- `unsigned()`, `comment()` and `after()` are accepted but ignored.
- Masonite-ORM features that have no Peewee counterpart are not emulated: relationship decorators, scopes, `__casts__` and factories. Use Peewee fields, backrefs and plain query methods instead.
- `Model.update(...)` / `Model.delete()` class-level queries bypass observers, timestamps and soft deletes. This is the same as in Peewee.
- The provider wraps `NotificationManager._format_notifiables` so that a `Collection` or query can be passed to `Notification.send()`.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev,mysql,postgres]"
.venv/bin/pytest                                       # SQLite only
```

To run the suite against MySQL 8.4 and Postgres 16 as well:

```bash
docker compose up -d --wait
TEST_DATABASES=sqlite,mysql,postgres .venv/bin/pytest
docker compose down
```

Every test that uses the `db` fixture runs once per backend. The containers listen on ports 3307 (MySQL) and 5433 (Postgres) so they don't clash with local servers. Override them with `MYSQL_PORT` / `POSTGRES_PORT`, set for both `docker compose` and `pytest`. Data lives in tmpfs and is discarded when the containers stop.
