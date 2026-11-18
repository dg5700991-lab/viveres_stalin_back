from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"

    def ready(self):
        from .hardening import endurecer_postgres
        # Se ejecuta tras cada `migrate`: RLS en todas las tablas y triggers anti-borrado.
        post_migrate.connect(endurecer_postgres, sender=self, dispatch_uid="core_endurecer_postgres")
