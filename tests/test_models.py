import json

import pytest

from masonite_peewee import Collection, ModelNotFound

from .conftest import Post, User


def make_user(i=0):
    return User.create({"name": "u{}".format(i), "email": "u{}@x.com".format(i), "password": "p"})


def test_table_names_are_pluralized():
    assert User._meta.table_name == "users"
    assert Post._meta.table_name == "posts"


def test_create_ignores_unknown_and_unfillable_keys(db):
    user = User.create({"name": "a", "email": "a@x.com", "bogus": 1})
    assert user.id and not hasattr(user, "bogus")


def test_guarded_attributes_are_not_filled(db):
    class Guarded(User):
        __guarded__ = ["name"]

    user = Guarded().fill({"name": "a", "email": "e"})
    assert user.name is None and user.email == "e"


def test_timestamps_are_maintained(db):
    user = make_user()
    created = user.created_at
    assert created is not None and user.updated_at is not None
    user.name = "changed"
    user.save()
    assert user.created_at == created and user.updated_at >= created


def test_serialize_hides_and_formats(db):
    user = make_user()
    data = user.serialize()
    assert "password" not in data
    assert isinstance(data["created_at"], str)
    assert json.loads(user.to_json())["email"] == "u0@x.com"


def test_serialize_foreign_keys_and_includes(db):
    user = make_user()
    Post.create(user=user, title="t")
    post = Post.select().first()
    assert post.serialize()["user_id"] == user.id
    assert user.serialize(include=["posts"])["posts"][0]["title"] == "t"


def test_appends(db):
    class WithAppends(User):
        __table__ = "users"
        __appends__ = ["display"]

        @property
        def display(self):
            return self.name.upper()

    WithAppends.create(name="a", email="a@x.com")
    assert WithAppends.first().serialize()["display"] == "A"


def test_compat_helpers(db):
    user = make_user()
    assert User.where("email", "u0@x.com").first().id == user.id
    assert User.where("id", ">", 0).count() == 1
    assert User.where({"name": "u0"}).first().id == user.id
    assert User.find(user.id).id == user.id
    assert isinstance(User.find([user.id]), Collection)
    assert User.get_table_name() == "users" and User.get_primary_key() == "id"
    assert user.get_primary_key_value() == user.id
    User.where("email", "u0@x.com").update({"name": "z"})
    assert User.find(user.id).name == "z"
    with pytest.raises(ModelNotFound):
        User.find_or_fail(999)


def test_collect_and_all(db):
    make_user(0), make_user(1)
    users = User.all()
    assert isinstance(users, Collection) and users.count() == 2
    assert users.pluck("email").all() == ["u0@x.com", "u1@x.com"]
    assert [u["name"] for u in users.serialize()] == ["u0", "u1"]


def test_length_aware_paginator(db):
    for i in range(5):
        make_user(i)
    page = User.select().order_by(User.id).paginator(2, page=2)
    assert [u.name for u in page] == ["u2", "u3"]
    assert page.serialize()["meta"] == {
        "total": 5,
        "next_page": 3,
        "count": 2,
        "previous_page": 1,
        "last_page": 3,
        "current_page": 2,
    }


def test_simple_paginator(db):
    for i in range(3):
        make_user(i)
    first = User.select().order_by(User.id).simple_paginator(2)
    assert first.count == 2 and first.has_more_pages()
    assert first.serialize()["meta"] == {"next_page": 2, "count": 2, "previous_page": None, "current_page": 1}
    last = User.select().order_by(User.id).simple_paginator(2, page=2)
    assert last.count == 1 and last.next_page is None


def test_paginator_reads_page_from_resolver(db, monkeypatch):
    from masonite_peewee import pagination

    for i in range(3):
        make_user(i)
    monkeypatch.setattr(pagination, "page_resolver", lambda: "2")
    assert User.select().paginator(2).current_page == 2


def test_soft_deletes(db):
    user = make_user()
    post = Post.create(user=user, title="t")
    post.delete_instance()
    assert Post.select().count() == 0
    assert Post.with_trashed().count() == 1
    assert Post.only_trashed().first().is_trashed
    assert Post.get_deleted_at_column() == "deleted_at"
    trashed = Post.with_trashed().first()
    trashed.restore()
    assert Post.select().count() == 1
    trashed.force_delete()
    assert Post.with_trashed().count() == 0


def test_observers(db):
    events = []

    class Observer:
        def creating(self, model):
            events.append("creating")

        def created(self, model):
            events.append("created")

        def updated(self, model):
            events.append("updated")

        def deleted(self, model):
            events.append("deleted")

    class Observed(User):
        __table__ = "users"

    Observed.observe(Observer())
    user = Observed.create(name="a", email="a@x.com")
    user.save()
    user.delete_instance()
    assert events == ["creating", "created", "updated", "deleted"]
    make_user(1)  # observers are per model class
    assert len(events) == 4
