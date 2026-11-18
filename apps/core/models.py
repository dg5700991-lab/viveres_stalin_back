import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class ErrorSoloAgregar(Exception):
    """Se intentó modificar o borrar un registro que es inmutable por diseño."""


class SoloAgregarQuerySet(models.QuerySet):
    """Bloquea UPDATE/DELETE masivos desde el ORM (en Postgres además lo bloquean triggers)."""

    def update(self, **kwargs):
        raise ErrorSoloAgregar("Registro inmutable: no se puede modificar.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ErrorSoloAgregar("Registro inmutable: no se puede modificar.")

    def delete(self):
        raise ErrorSoloAgregar("Registro inmutable: no se puede borrar.")


class ModeloUUID(models.Model):
    """Base: clave UUID (no adivinable, evita enumerar registros) + fechas."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoloAgregarModel(models.Model):
    """
    Libros contables (movimientos de inventario, fiados, caja, auditoría).
    Solo se insertan; las correcciones se hacen con un nuevo movimiento que compensa.
    """
    APPEND_ONLY = True
    objects = SoloAgregarQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ErrorSoloAgregar("Registro inmutable: no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ErrorSoloAgregar("Registro inmutable: no se puede borrar.")


class AuditLog(SoloAgregarModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.PROTECT, related_name="+")
    accion = models.CharField(max_length=60, db_index=True)
    entidad = models.CharField(max_length=60)
    entidad_id = models.CharField(max_length=64)
    detalle = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)

    class Meta:
        ordering = ["-fecha"]
        indexes = [models.Index(fields=["entidad", "entidad_id"])]

    def __str__(self):
        return f"{self.fecha:%Y-%m-%d %H:%M} {self.accion} {self.entidad}:{self.entidad_id}"
