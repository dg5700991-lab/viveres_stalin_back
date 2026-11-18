import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.constantes import MetodoPago


class EstadoVenta(models.TextChoices):
    COMPLETADA = "COMPLETADA", "Completada"
    ANULADA = "ANULADA", "Anulada"


class OrigenVenta(models.TextChoices):
    MOSTRADOR = "MOSTRADOR", "Mostrador"
    PEDIDO = "PEDIDO", "Pedido anticipado"


class Venta(models.Model):
    """id autoincremental = n.º de ticket. Las ventas no se editan ni se borran: se anulan."""
    idempotency_key = models.UUIDField(unique=True)  # evita cobrar dos veces si el cajero reintenta
    turno = models.ForeignKey("caja.Turno", on_delete=models.PROTECT, related_name="ventas")
    cajero = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    cliente = models.ForeignKey("clientes.Cliente", null=True, blank=True, on_delete=models.PROTECT,
                                related_name="ventas")
    origen = models.CharField(max_length=10, choices=OrigenVenta.choices, default=OrigenVenta.MOSTRADOR)
    estado = models.CharField(max_length=10, choices=EstadoVenta.choices, default=EstadoVenta.COMPLETADA)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    nombre_fiado = models.CharField(max_length=150, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    anulada_en = models.DateTimeField(null=True, blank=True)
    anulada_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.PROTECT, related_name="+")
    motivo_anulacion = models.CharField(max_length=200, blank=True)
    nombre_fiado = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["-id"]
        constraints = [models.CheckConstraint(condition=Q(total__gt=0), name="venta_total_positivo")]


class DetalleVenta(models.Model):
    """Copia (snapshot) del nombre y precio al momento de vender: cambiar el precio no altera el pasado."""
    venta = models.ForeignKey(Venta, on_delete=models.PROTECT, related_name="detalles")
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT, related_name="+")
    nombre_producto = models.CharField(max_length=150)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0)])
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(cantidad__gt=0), name="detalle_cantidad_positiva")]


class Pago(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.PROTECT, related_name="pagos")
    metodo = models.CharField(max_length=14, choices=MetodoPago.choices)
    monto = models.DecimalField(max_digits=12, decimal_places=2)
    referencia = models.CharField(max_length=60, blank=True)  # comprobante (obligatorio en transferencia)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(monto__gt=0), name="pago_monto_positivo")]
