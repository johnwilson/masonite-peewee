from masonite.middleware import Middleware

from .connections import get_manager


class DatabaseConnectionMiddleware(Middleware):
    """Closes the request's database connections when it finishes (returning
    them to the pool for pooled connections). Peewee reconnects lazily."""

    def before(self, request, response):
        return request

    def after(self, request, response):
        get_manager().close_all()
        return request
