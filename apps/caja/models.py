import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.models import ErrorSoloAgregar, ModeloUUID, SoloAgregarModel


class EstadoTurno(models.TextChoices):
    ABIERTO = "ABIERTO", "Abierto"
    CERRADO = "CERRADO", "Cerrado"


class Turno(ModeloUUID):
    cajero = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="turnos")
    estado = models.CharField(max_length=7, choices=EstadoTurno.choices, default=EstadoTurno.ABIERTO)
    fondo_inicial = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    cerrado_en = models.DateTimeField(null=True, blank=True)
    # Foto del cuadre al cerrar (queda congelada):
    esperado_efectivo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    esperado_transferencia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    contado_efectivo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    contado_transferencia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    diferencia_efectivo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    diferencia_transferencia = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    notas_cierre = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-creado_en"]
        constraints = [models.UniqueConstraint(fields=["cajero"], condition=Q(estado="ABIERTO"),
                                               name="un_turno_abierto_por_cajero")]

    def save(self, *args, **kwargs):
        # Un turno cerrado es inmutable: el cuadre no se "maquilla" después.
        if not self._state.adding and Turno.objects.filter(pk=self.pk, estado=EstadoTurno.CERRADO).exists():
            raise ErrorSoloAgregar("Un turno cerrado no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ErrorSoloAgregar("Los turnos no se borran.")


class TipoMovCaja(models.TextChoices):
    INGRESO = "INGRESO", "Ingreso de efectivo"
    EGRESO = "EGRESO", "Retiro / pago desde caja"


class MovimientoCaja(SoloAgregarModel):
    """Entradas/salidas de efectivo que no son ventas (pago a un proveedor, cambio extra, etc.)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    turno = models.ForeignKey(Turno, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=7, choices=TipoMovCaja.choices)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    motivo = models.CharField(max_length=200)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["creado_en"]
        constraints = [models.CheckConstraint(condition=Q(monto__gt=0), name="movcaja_monto_positivo")]
