from .conftest import User


def seed():
    for i in range(3):
        User.create(name="u{}".format(i), email="u{}@x.com".format(i))


def test_reads_return_dicts(db):
    seed()
    builder = db.get_query_builder()
    assert builder.table("users").where("email", "u1@x.com").first()["name"] == "u1"
    rows = builder.table("users").where("id", ">=", 2).order_by("id", "desc").limit(1).get()
    assert [r["name"] for r in rows] == ["u2"]
    assert builder.table("users").where({"name": "u0"}).count() == 1
    assert builder.table("users").where_in("id", [1, 2]).count() == 2
    assert builder.table("users").where_null("password").count() == 3
    assert builder.table("users").where_not_null("password").get() == []


def test_clauses_reset_after_execution_but_table_is_kept(db):
    seed()
    builder = db.get_query_builder().table("users")
    assert builder.where("id", 1).count() == 1
    assert builder.count() == 3


def test_where_before_table(db):
    # Masonite's queue driver chains builder.where(...).table(...).update(...)
    seed()
    builder = db.get_query_builder().table("other")
    builder.where("id", 1).table("users").update({"name": "z"})
    assert User.get_by_id(1).name == "z"


def test_new_keeps_table_and_connection(db):
    seed()
    builder = db.get_query_builder().on(db.resolve_name()).table("users")
    assert builder.new().count() == 3


def test_writes(db):
    builder = db.get_query_builder().table("users")
    record = builder.create({"name": "a", "email": "a@x.com"})
    assert record["id"] == 1
    assert builder.where("id", 1).update({"name": "b"}) == 1
    assert builder.where("id", 1).delete() == 1
    assert builder.count() == 0


def test_transactions(db):
    seed()
    db.begin_transaction()
    db.get_query_builder().table("users").delete()
    assert User.select().count() == 0
    db.rollback()
    assert User.select().count() == 3

    db.begin_transaction()
    User.create(name="x", email="x@x.com")
    db.commit()
    assert User.select().count() == 4


def test_default_connection_switch_repoints_models(db):
    for name in db._databases:
        db._connection_details["default"] = name
        assert User._meta.database.obj is db._databases[name]
