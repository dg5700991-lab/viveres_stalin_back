import uuid

from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from apps.core.models import ModeloUUID


class TipoProducto(models.TextChoices):
    CODIGO = "CODIGO", "Con código de barras"
    GRANEL = "GRANEL", "A granel / sin código"


class Unidad(models.TextChoices):
    UNIDAD = "UND", "Unidad"
    LIBRA = "LB", "Libra"
    KILO = "KG", "Kilo"
    LITRO = "L", "Litro"
    DOCENA = "DOC", "Docena"


def ruta_imagen(instancia, nombre):
    # El nombre original del usuario se descarta: nunca llega al sistema de archivos.
    return f"productos/{uuid.uuid4().hex}.webp"


class Categoria(ModeloUUID):
    nombre = models.CharField(max_length=60, unique=True)
    descripcion = models.CharField(max_length=200, blank=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Producto(ModeloUUID):
    categoria = models.ForeignKey(Categoria, null=True, blank=True, on_delete=models.SET_NULL, related_name="productos")
    tipo = models.CharField(max_length=6, choices=TipoProducto.choices)
    nombre = models.CharField(max_length=150, db_index=True)
    codigo_barras = models.CharField(
        max_length=32, null=True, blank=True, unique=True,
        validators=[RegexValidator(r"^[A-Za-z0-9\-]{4,32}$", "Código inválido.")])
    unidad_medida = models.CharField(max_length=3, choices=Unidad.choices, default=Unidad.UNIDAD)
    precio_venta = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    costo = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    # Caché del stock: solo cambia mediante inventario.services (cada cambio deja un movimiento).
    stock_actual = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    stock_minimo = models.DecimalField(max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(0)])
    imagen = models.ImageField(upload_to=ruta_imagen, null=True, blank=True)
    activo = models.BooleanField(default=True)  # los productos NO se borran: se desactivan

    class Meta:
        ordering = ["nombre"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(tipo="CODIGO", codigo_barras__isnull=False) |
                           Q(tipo="GRANEL", codigo_barras__isnull=True)),
                name="producto_codigo_segun_tipo"),
            models.CheckConstraint(condition=Q(precio_venta__gte=0), name="producto_precio_no_negativo"),
            models.UniqueConstraint(fields=["nombre"], condition=Q(tipo="GRANEL"),
                                    name="producto_granel_nombre_unico"),
        ]
        indexes = [models.Index(fields=["tipo", "activo"])]

    def save(self, *args, **kwargs):
        if not self.codigo_barras:
            self.codigo_barras = None
        super().save(*args, **kwargs)

    @property
    def stock_bajo(self):
        return self.stock_actual <= self.stock_minimo

    def __str__(self):
        return self.nombre
