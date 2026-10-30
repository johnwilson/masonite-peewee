"""Database notifications on Peewee: replaces masonite.notification's
DatabaseNotification model and Notifiable mixin, which import masonite-orm."""
from peewee import CharField, DateTimeField, IntegerField, TextField

from .models import Model, utcnow

# notifiable_type -> model class, for tables whose model can't be found by name
morph_map = {}


def _subclasses(cls):
    for subclass in cls.__subclasses__():
        yield subclass
        yield from _subclasses(subclass)


def resolve_morph(table):
    if table in morph_map:
        return morph_map[table]
    for model in _subclasses(Model):
        if model._meta.table_name == table:
            return model
    raise LookupError("No model found for notifiable_type '{}'".format(table))


class DatabaseNotification(Model):
    """A notification stored by the "database" notification driver."""

    __table__ = "notifications"

    id = CharField(primary_key=True, max_length=36)
    type = CharField()
    data = TextField()
    notifiable_id = IntegerField()
    notifiable_type = CharField()
    read_at = DateTimeField(null=True)
    created_at = DateTimeField(null=True)
    updated_at = DateTimeField(null=True)

    @property
    def notifiable(self):
        """The model instance the notification was sent to."""
        return resolve_morph(self.notifiable_type).find(self.notifiable_id)

    def mark_as_read(self):
        if not self.read_at:
            self.read_at = utcnow()
            return self.save()

    def mark_as_unread(self):
        if self.read_at:
            self.read_at = None
            return self.save()

    @property
    def is_read(self):
        return self.read_at is not None

    @property
    def is_unread(self):
        return self.read_at is None


class Notifiable:
    """Mixin allowing notifications to be sent to a model.

    Usage:
        user.notify(WelcomeNotification())
    """

    def notify(self, notification, drivers=[], dry=False, fail_silently=False):
        """Send the given notification."""
        from wsgi import application

        if hasattr(notification, "send"):
            notification.send(notification, drivers, dry, fail_silently)

        return application.make("notification").send(self, notification, drivers, dry, fail_silently)

    def route_notification_for(self, driver):
        """Routing information for a driver: route_notification_for_<driver>()
        when defined, otherwise the email field for mail."""
        method = getattr(self, "route_notification_for_{}".format(driver), None)
        if method:
            return method()
        if driver == "database":
            return None
        if driver == "mail":
            return self.email
        from masonite.exceptions import NotificationException

        raise NotificationException(
            "Notifiable model does not implement route_notification_for_{}".format(driver)
        )

    @property
    def notifications(self):
        """Notifications stored for this model, newest first."""
        return (
            DatabaseNotification.select()
            .where(
                DatabaseNotification.notifiable_id == self.get_primary_key_value(),
                DatabaseNotification.notifiable_type == self.get_table_name(),
            )
            .order_by(DatabaseNotification.created_at.desc())
        )

    @property
    def unread_notifications(self):
        return self.notifications.where(DatabaseNotification.read_at.is_null())

    @property
    def read_notifications(self):
        return self.notifications.where(DatabaseNotification.read_at.is_null(False))
