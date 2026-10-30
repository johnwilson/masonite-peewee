"""Translate Masonite style where(column, [operator], value) calls into Peewee expressions."""
from peewee import OP, Expression

OPERATORS = {
    "=": OP.EQ,
    "==": OP.EQ,
    "!=": OP.NE,
    "<>": OP.NE,
    "<": OP.LT,
    "<=": OP.LTE,
    ">": OP.GT,
    ">=": OP.GTE,
    "like": OP.LIKE,
    "ilike": OP.ILIKE,
}


def split_where_args(args):
    """Accept (value,) or (operator, value), as masonite-orm does."""
    if len(args) == 1:
        return "=", args[0]
    if len(args) == 2:
        return args[0], args[1]
    raise TypeError("where() takes a column and either a value or an operator and a value")


def build_condition(column, operator, value):
    operator = operator.strip().lower()
    if value is None and operator in ("=", "==", "is"):
        return column.is_null()
    if value is None and operator in ("!=", "<>", "is not"):
        return column.is_null(False)
    if operator == "in":
        return column.in_(list(value))
    if operator == "not in":
        return column.not_in(list(value))
    if operator == "not like":
        return ~Expression(column, OP.LIKE, value)
    if operator not in OPERATORS:
        raise ValueError("Unsupported operator '{}'".format(operator))
    return Expression(column, OPERATORS[operator], value)


def build_conditions(resolve_column, column, args):
    """Return a list of expressions for where(dict) or where(column, [op], value)."""
    if isinstance(column, dict):
        return [build_condition(resolve_column(key), "=", value) for key, value in column.items()]
    operator, value = split_where_args(args)
    return [build_condition(resolve_column(column), operator, value)]
