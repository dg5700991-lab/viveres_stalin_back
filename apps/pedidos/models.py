from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.models import ModeloUUID


class EstadoPedido(models.TextChoices):
    PENDIENTE = "PENDIENTE", "Pendiente (nuevo)"
    EN_PREPARACION = "EN_PREPARACION", "En preparación"
    LISTO = "LISTO", "Listo para recoger"
    ENTREGADO = "ENTREGADO", "Entregado y cobrado"
    CANCELADO = "CANCELADO", "Cancelado"


class Pedido(ModeloUUID):
    cliente = models.ForeignKey("clientes.Cliente", on_delete=models.PROTECT, related_name="pedidos")
    estado = models.CharField(max_length=14, choices=EstadoPedido.choices, default=EstadoPedido.PENDIENTE,
                              db_index=True)
    notas = models.CharField(max_length=300, blank=True)
    hora_estimada_recogida = models.DateTimeField(null=True, blank=True)
    total_estimado = models.DecimalField(max_digits=12, decimal_places=2)  # precios vigentes al pedir
    # Alarma: la pantalla del personal suena mientras haya pedidos con alarma_pendiente=True.
    alarma_pendiente = models.BooleanField(default=True, db_index=True)
    atendido_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.PROTECT, related_name="+")
    venta = models.OneToOneField("ventas.Venta", null=True, blank=True, on_delete=models.PROTECT,
                                 related_name="pedido")  # se llena al cobrar en tienda

    class Meta:
        ordering = ["-creado_en"]
        constraints = [models.CheckConstraint(condition=Q(total_estimado__gt=0), name="pedido_total_positivo")]


class DetallePedido(models.Model):
    pedido = models.ForeignKey(Pedido, on_delete=models.PROTECT, related_name="detalles")
    producto = models.ForeignKey("catalogo.Producto", on_delete=models.PROTECT, related_name="+")
    nombre_producto = models.CharField(max_length=150)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(0)])
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
