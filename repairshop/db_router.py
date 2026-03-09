from django.conf import settings

from .tenant_context import get_current_db


class TenantDatabaseRouter:
    """
    Route tenant app reads/writes to the current tenant DB alias.

    Shared apps always stay on `default`.
    """

    def _is_shared_app(self, model):
        return model._meta.app_label in getattr(settings, "SHARED_APPS", set())

    def db_for_read(self, model, **hints):
        if self._is_shared_app(model):
            return "default"
        return get_current_db()

    def db_for_write(self, model, **hints):
        if self._is_shared_app(model):
            return "default"
        return get_current_db()

    def allow_relation(self, obj1, obj2, **hints):
        db1 = getattr(obj1._state, "db", None)
        db2 = getattr(obj2._state, "db", None)
        if db1 and db2:
            return db1 == db2
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        shared_apps = getattr(settings, "SHARED_APPS", set())

        # Shared metadata apps (auth, admin, users, shops) migrate only on default.
        if app_label in shared_apps:
            return db == "default"

        # Tenant-domain apps migrate on tenant DBs (not default).
        return db != "default"
