"""Switch a Masonite 5 project from masonite-orm to masonite-peewee.

Every step is idempotent: running the installer twice changes nothing the
second time. A step that cannot find what it expects (because the file was
customised) is reported as skipped, so it can be finished by hand."""
import json
import os
import re
from importlib import metadata
from urllib.parse import unquote, urlparse

UPDATED, UNCHANGED, SKIPPED = "updated", "unchanged", "skipped"

USER_MODEL = '''"""User Model."""

from peewee import CharField, DateTimeField

from masonite.authentication import Authenticates
from masonite.authorization import Authorizes
from masonite_peewee import Model
from masonite_peewee.notifications import Notifiable


class User(Model, Authenticates, Authorizes, Notifiable):
    """User Model."""

    __fillable__ = ["name", "email", "password", "phone"]
    __hidden__ = ["password"]
    __auth__ = "email"

    name = CharField()
    email = CharField(unique=True)
    password = CharField()
    second_password = CharField(null=True)
    remember_token = CharField(null=True)
    phone = CharField(null=True)
    verified_at = DateTimeField(null=True)
    created_at = DateTimeField(null=True)
    updated_at = DateTimeField(null=True)
'''

STOCK_USER_MODEL = '''"""User Model."""

from masoniteorm.models import Model
from masonite.authentication import Authenticates
from masonite.authorization import Authorizes
from masonite.notification import Notifiable


class User(Model, Authenticates, Authorizes, Notifiable):
    """User Model."""

    __fillable__ = ["name", "email", "password", "phone"]
    __hidden__ = ["password"]
    __auth__ = "email"
'''

BUILDER_BINDING = re.compile(
    r"[ \t]*from masoniteorm\.query import QueryBuilder\n\s*"
    r"self\.application\.bind\(\s*\"builder\",\s*QueryBuilder\([^\n]*\n\s*\)\n(\s*\n)?"
)
RESOLVER_BINDING = re.compile(r"\n?[ \t]*self\.application\.bind\(\"resolver\", config\(\"database\.db\"\)\)\n")
MIDDLEWARE_IMPORT = "from masonite_peewee.middleware import DatabaseConnectionMiddleware\n"


def default_requirement():
    """The requirements.txt line for masonite-peewee.

    A project generated from a local checkout (pip install -e . or a path)
    points back at that checkout, otherwise the released version is pinned."""
    try:
        dist = metadata.distribution("masonite-peewee")
    except metadata.PackageNotFoundError:
        return "masonite-peewee"
    direct_url = dist.read_text("direct_url.json")
    if direct_url:
        info = json.loads(direct_url)
        if info.get("url", "").startswith("file://"):
            path = unquote(urlparse(info["url"]).path)
            if info.get("dir_info", {}).get("editable"):
                return "-e {}".format(path)
            return "masonite-peewee @ {}".format(info["url"])
    return "masonite-peewee>={}".format(dist.version)


class ProjectInstaller:
    def __init__(self, root, requirement=None):
        self.root = os.path.abspath(root)
        self.requirement = requirement or default_requirement()
        self.results = []

    def is_masonite_project(self):
        return all(
            os.path.isfile(self.path(name)) for name in ("craft", "config/database.py", "app/Kernel.py")
        )

    def run(self):
        for step in (
            self.database_config,
            self.providers,
            self.kernel,
            self.queue_and_notification_connections,
            self.user_model,
            self.migrations_and_seeders,
            self.notifications_migration,
            self.requirements,
        ):
            step()
        self.leftover_references()
        return self.results

    # helpers
    def path(self, relative):
        return os.path.join(self.root, *relative.split("/"))

    def read(self, relative):
        with open(self.path(relative)) as fp:
            return fp.read()

    def write(self, relative, content):
        with open(self.path(relative), "w") as fp:
            fp.write(content)

    def report(self, status, relative, message):
        self.results.append((status, relative, message))

    def rewrite(self, relative, transform, message):
        """Apply transform(content) -> content, or a (status, reason) tuple to skip."""
        if not os.path.isfile(self.path(relative)):
            return self.report(SKIPPED, relative, "file not found")
        content = self.read(relative)
        result = transform(content)
        if isinstance(result, tuple):
            return self.report(*result[:1], relative, result[1])
        if result == content:
            return self.report(UNCHANGED, relative, message)
        self.write(relative, result)
        self.report(UPDATED, relative, message)

    # steps
    def database_config(self):
        def transform(content):
            if "DatabaseManager(DATABASES)" in content:
                return content
            if "ConnectionResolver" not in content:
                return (SKIPPED, "no ConnectionResolver found; set DB = DatabaseManager(DATABASES)")
            content = content.replace(
                "from masoniteorm.connections import ConnectionResolver",
                "from masonite_peewee import DatabaseManager",
            )
            return re.sub(r"ConnectionResolver\(\)\.set_connection_details\((\w+)\)", r"DatabaseManager(\1)", content)

        self.rewrite("config/database.py", transform, "DB = DatabaseManager(DATABASES)")

    def providers(self):
        def transform(content):
            if "PeeweeProvider" in content:
                return content
            if not re.search(r"^\s+ORMProvider,\n", content, re.M):
                return (SKIPPED, "ORMProvider not found; add PeeweeProvider to PROVIDERS by hand")
            # the first occurrence is the import, the second the PROVIDERS entry
            content = re.sub(r"^\s+ORMProvider,\n", "", content, count=1, flags=re.M)
            content = re.sub(r"^(\s+)ORMProvider,\n", r"\1PeeweeProvider,\n", content, count=1, flags=re.M)
            return re.sub(
                r"^(from masonite\.providers import \([^)]*\)\n)",
                r"\1from masonite_peewee.provider import PeeweeProvider\n",
                content,
                count=1,
                flags=re.M,
            )

        self.rewrite("config/providers.py", transform, "ORMProvider replaced with PeeweeProvider")

    def kernel(self):
        def transform(content):
            content = BUILDER_BINDING.sub("", content)
            content = RESOLVER_BINDING.sub("", content)
            if "DatabaseConnectionMiddleware" not in content:
                if "http_middleware = [\n" not in content:
                    return (SKIPPED, "http_middleware list not found; add DatabaseConnectionMiddleware by hand")
                content = content.replace(
                    "http_middleware = [\n", "http_middleware = [\n        DatabaseConnectionMiddleware,\n", 1
                )
                content = MIDDLEWARE_IMPORT + content
            if "masoniteorm" in content:
                return (SKIPPED, "masoniteorm bindings left in register_database(); remove them by hand")
            return content

        self.rewrite(
            "app/Kernel.py",
            transform,
            "masonite-orm bindings removed, DatabaseConnectionMiddleware added",
        )

    def queue_and_notification_connections(self):
        # the stock configs hard-code the sqlite connection for the database drivers
        for relative in ("config/queue.py", "config/notification.py"):
            self.rewrite(
                relative,
                lambda content: content.replace('"connection": "sqlite"', '"connection": "default"'),
                "database driver uses the default connection",
            )

    def user_model(self):
        def transform(content):
            if "masonite_peewee" in content:
                return content
            if content.strip() != STOCK_USER_MODEL.strip():
                return (SKIPPED, "customised model; declare its fields with Peewee by hand")
            return USER_MODEL

        self.rewrite("app/models/User.py", transform, "rewritten as a Peewee model")

    def migrations_and_seeders(self):
        replacements = {
            "from masoniteorm.migrations import Migration": "from masonite_peewee.migrations import Migration",
            "from masoniteorm.seeds import Seeder": "from masonite_peewee.seeds import Seeder",
        }

        def transform(content):
            for old, new in replacements.items():
                content = content.replace(old, new)
            return content

        for directory in ("databases/migrations", "databases/seeds"):
            if not os.path.isdir(self.path(directory)):
                continue
            for name in sorted(os.listdir(self.path(directory))):
                if name.endswith(".py"):
                    self.rewrite("{}/{}".format(directory, name), transform, "imports switched to masonite_peewee")

    def notifications_migration(self):
        # Masonite stores uuid strings as notification ids
        directory = "databases/migrations"
        if not os.path.isdir(self.path(directory)):
            return
        for name in sorted(os.listdir(self.path(directory))):
            if name.endswith("_create_notifications_table.py"):
                self.rewrite(
                    "{}/{}".format(directory, name),
                    lambda content: content.replace(
                        'table.big_increments("id").primary()', 'table.string("id", 36).primary()'
                    ),
                    "notification id is a 36 character string",
                )

    def requirements(self):
        def transform(content):
            if re.search(r"^(-e .*masonite-peewee.*|masonite[-_]peewee\b.*)$", content, re.M | re.I):
                return content
            if content and not content.endswith("\n"):
                content += "\n"
            return content + self.requirement + "\n"

        if not os.path.isfile(self.path("requirements.txt")):
            return self.report(SKIPPED, "requirements.txt", "file not found; pip install masonite-peewee")
        self.rewrite("requirements.txt", transform, "added {}".format(self.requirement))

    def leftover_references(self):
        reported = {relative for status, relative, _ in self.results if status == SKIPPED}
        for directory in ("app", "config", "databases", "routes", "tests"):
            for dirpath, dirnames, filenames in os.walk(self.path(directory)):
                dirnames[:] = [d for d in dirnames if d != "__pycache__"]
                for name in filenames:
                    if not name.endswith(".py"):
                        continue
                    path = os.path.join(dirpath, name)
                    relative = os.path.relpath(path, self.root).replace(os.sep, "/")
                    with open(path) as fp:
                        if "masoniteorm" in fp.read() and relative not in reported:
                            self.report(SKIPPED, relative, "still imports masoniteorm")


def install(root, requirement=None):
    return ProjectInstaller(root, requirement).run()
