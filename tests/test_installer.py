import os
import shutil

import pytest
from cleo.testers.command_tester import CommandTester
from masonite.utils.filesystem import get_module_dir

import masonite.commands
from masonite_peewee.cli import InstallCommand, NewProjectCommand
from masonite_peewee.installer import SKIPPED, UNCHANGED, ProjectInstaller

SKELETON = os.path.join(get_module_dir(masonite.commands.__file__), "..", "skeleton")


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "app"
    shutil.copytree(SKELETON, root, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return root


def orm_references(root):
    found = []
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            path = os.path.join(dirpath, name)
            if name.endswith(".py") and "masoniteorm" in open(path).read():
                found.append(os.path.relpath(path, root))
    return found


def test_converts_the_stock_skeleton(project):
    results = ProjectInstaller(str(project), "masonite-peewee").run()
    assert [r for r in results if r[0] == SKIPPED] == []
    assert orm_references(project) == []

    assert "DB = DatabaseManager(DATABASES)" in (project / "config/database.py").read_text()
    providers = (project / "config/providers.py").read_text()
    assert "ORMProvider" not in providers and "    PeeweeProvider,\n" in providers
    kernel = (project / "app/Kernel.py").read_text()
    assert "DatabaseConnectionMiddleware," in kernel and '"resolver"' not in kernel
    assert '"connection": "default"' in (project / "config/queue.py").read_text()
    assert "email = CharField(unique=True)" in (project / "app/models/User.py").read_text()
    assert (project / "requirements.txt").read_text().endswith("masonite-peewee\n")
    compile((project / "app/Kernel.py").read_text(), "Kernel.py", "exec")
    compile((project / "config/providers.py").read_text(), "providers.py", "exec")


def test_is_idempotent(project):
    ProjectInstaller(str(project), "masonite-peewee").run()
    results = ProjectInstaller(str(project), "masonite-peewee").run()
    assert {status for status, _, _ in results} == {UNCHANGED}
    assert (project / "requirements.txt").read_text().count("masonite-peewee") == 1


def test_customised_files_are_skipped_not_overwritten(project):
    user = project / "app/models/User.py"
    user.write_text(user.read_text() + "\n    def custom(self):\n        pass\n")
    results = ProjectInstaller(str(project), "masonite-peewee").run()
    assert (SKIPPED, "app/models/User.py", "customised model; declare its fields with Peewee by hand") in results
    assert "masoniteorm" in user.read_text()


def test_install_command(project):
    tester = CommandTester(InstallCommand())
    assert tester.execute("{} --requirement=masonite-peewee==0.1.0".format(project)) == 0
    assert "masonite-peewee==0.1.0" in (project / "requirements.txt").read_text()
    assert CommandTester(InstallCommand()).execute(str(project / "missing")) == 1


def test_new_command(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tester = CommandTester(NewProjectCommand())
    tester.execute("app --db=mysql --no-input --no-venv --no-git --preset=none --requirement=masonite-peewee")
    assert orm_references(tmp_path / "app") == []
    requirements = (tmp_path / "app/requirements.txt").read_text()
    assert "pymysql" in requirements and "masonite-peewee" in requirements
    assert "DB_CONNECTION=mysql" in (tmp_path / "app/.env").read_text()
