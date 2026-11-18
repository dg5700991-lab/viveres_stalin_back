import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.constantes import MetodoPago
from apps.core.models import ModeloUUID, SoloAgregarModel


class Cliente(ModeloUUID):
    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.PROTECT, related_name="cliente")
    nombre = models.CharField(max_length=120, db_index=True)
    apellidos = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    documento = models.CharField(max_length=20, blank=True)
    limite_credito = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
                                         validators=[MinValueValidator(0)])  # null = sin límite
    saldo_fiado = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # caché del libro de fiados
    apellidos = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    notas = models.CharField(max_length=300, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]
        constraints = [
            models.CheckConstraint(condition=Q(saldo_fiado__gte=0), name="cliente_saldo_no_negativo"),
            models.UniqueConstraint(fields=["telefono"], condition=~Q(telefono=""), name="cliente_telefono_unico"),
        ]

    def __str__(self):
        return self.nombre


class TipoFiado(models.TextChoices):
    CARGO = "CARGO", "Cargo (venta a fiado)"
    ABONO = "ABONO", "Abono (pago del cliente)"
    REVERSO = "REVERSO", "Reverso por anulación de venta"


class MovimientoFiado(SoloAgregarModel):
    """Libreta digital: cada cargo/abono es un renglón inmutable con el saldo resultante."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True, db_index=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=8, choices=TipoFiado.choices)
    monto = models.DecimalField(max_digits=12, decimal_places=2)  # siempre positivo
    saldo_resultante = models.DecimalField(max_digits=12, decimal_places=2)
    metodo_pago = models.CharField(max_length=14, choices=MetodoPago.choices, blank=True)  # solo en abonos
    referencia = models.CharField(max_length=60, blank=True)  # n.º de comprobante de la transferencia
    venta = models.ForeignKey("ventas.Venta", null=True, blank=True, on_delete=models.PROTECT,
                              related_name="movimientos_fiado")
    turno = models.ForeignKey("caja.Turno", null=True, blank=True, on_delete=models.PROTECT,
                              related_name="abonos")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ["-creado_en"]
        constraints = [models.CheckConstraint(condition=Q(monto__gt=0), name="fiado_monto_positivo")]
        indexes = [models.Index(fields=["cliente", "-creado_en"])]
