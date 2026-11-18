import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import SoloAgregarModel


class TipoMovimiento(models.TextChoices):
    ENTRADA = "ENTRADA", "Entrada (compra / reposición)"
    SALIDA_VENTA = "SALIDA_VENTA", "Salida por venta"
    ANULACION_VENTA = "ANULACION_VENTA", "Reingreso por anulación de venta"
    AJUSTE = "AJUSTE", "Ajuste por conteo físico"
    MERMA = "MERMA", "Merma / pérdida"


class MovimientoInventario(SoloAgregarModel):
    """Libro de inventario: cantidad con signo (+ entra, − sale). Explica TODA diferencia de stock."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=20, choices=TipoMovimiento.choices)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    stock_resultante = models.DecimalField(max_digits=12, decimal_places=3)
    costo_unitario = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    motivo = models.CharField(max_length=200, blank=True)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    venta = models.ForeignKey("ventas.Venta", null=True, blank=True, on_delete=models.PROTECT,
                              related_name="movimientos_inventario")

    class Meta:
        ordering = ["-creado_en"]
        constraints = [models.CheckConstraint(condition=~Q(cantidad=0), name="movimiento_cantidad_no_cero")]
        indexes = [models.Index(fields=["producto", "-creado_en"])]
