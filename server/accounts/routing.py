class AuthenticationRouter:
    """Only account/session models use the narrow authentication connection."""
    labels = {"accounts", "sessions"}

    def db_for_read(self, model, **hints):
        if model._meta.app_label in self.labels:
            return "auth"
        return None

    db_for_write = db_for_read

    def allow_relation(self, obj1, obj2, **hints):
        if obj1._meta.app_label in self.labels and obj2._meta.app_label in self.labels:
            return True
        return None

    def allow_migrate(self, db, app_label, **hints):
        # Application roles never migrate. The separate migration/test connection does.
        return db == "default"
