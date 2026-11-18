from decimal import Decimal

from rest_framework import serializers

from apps.core.constantes import MetodoPago

from .models import DetalleVenta, Pago, Venta


class CotizacionItemSerializer(serializers.Serializer):
    producto = serializers.UUIDField()
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"),
                                        max_value=Decimal("100000"))


class CotizacionRequestSerializer(serializers.Serializer):
    items = CotizacionItemSerializer(many=True, allow_empty=False, max_length=200)
    efectivo_recibido = serializers.DecimalField(max_digits=12, decimal_places=2, required=False,
                                                 allow_null=True, min_value=Decimal("0"))


class ItemEntradaSerializer(serializers.Serializer):
    producto = serializers.UUIDField()
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"),
                                        max_value=Decimal("100000"))


class PagoEntradaSerializer(serializers.Serializer):
    metodo = serializers.ChoiceField(choices=MetodoPago.choices)
    monto = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
                                     max_value=Decimal("9999999"))
    referencia = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")


class VentaCrearSerializer(serializers.Serializer):
    items = ItemEntradaSerializer(many=True, allow_empty=False, max_length=200)
    pagos = PagoEntradaSerializer(many=True, allow_empty=False, max_length=4)
    cliente = serializers.UUIDField(required=False, allow_null=True)
    idempotency_key = serializers.UUIDField()
    efectivo_recibido = serializers.DecimalField(max_digits=12, decimal_places=2, required=False,
                                                 min_value=Decimal("0"), max_value=Decimal("9999999"))
    nombre_fiado = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")


class DetalleSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetalleVenta
        fields = ["producto", "nombre_producto", "cantidad", "precio_unitario", "subtotal"]


class PagoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pago
        fields = ["metodo", "monto", "referencia"]


class VentaSerializer(serializers.ModelSerializer):
    detalles = DetalleSerializer(many=True, read_only=True)
    pagos = PagoSerializer(many=True, read_only=True)
    cajero_nombre = serializers.CharField(source="cajero.username", read_only=True)
    cliente_nombre = serializers.CharField(source="cliente.nombre", read_only=True, default=None)
    vuelto = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True, default=Decimal("0.00"))

    class Meta:
        model = Venta
        fields = ["id", "estado", "origen", "total", "creado_en", "cajero_nombre", "cliente", "cliente_nombre",
                  "turno", "detalles", "pagos", "vuelto", "anulada_en", "motivo_anulacion", "nombre_fiado"]


class AnulacionSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=200)
