from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.ventas.serializers import ItemEntradaSerializer, PagoEntradaSerializer

from .models import DetallePedido, EstadoPedido, Pedido


class DetallePedidoSerializer(serializers.ModelSerializer):
    class Meta:
        model = DetallePedido
        fields = ["producto", "nombre_producto", "cantidad", "precio_unitario", "subtotal"]


class PedidoSerializer(serializers.ModelSerializer):
    detalles = DetallePedidoSerializer(many=True, read_only=True)
    cliente_nombre = serializers.CharField(source="cliente.nombre", read_only=True)

    class Meta:
        model = Pedido
        fields = ["id", "estado", "creado_en", "cliente", "cliente_nombre", "notas", "hora_estimada_recogida",
                  "total_estimado", "alarma_pendiente", "venta", "detalles"]


class PedidoCrearSerializer(serializers.Serializer):
    items = ItemEntradaSerializer(many=True, allow_empty=False, max_length=50)
    notas = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    hora_estimada_recogida = serializers.DateTimeField(required=False, allow_null=True)

    def validate_hora_estimada_recogida(self, v):
        if v and v < timezone.now():
            raise serializers.ValidationError("La hora de recogida debe ser futura.")
        return v


class CambioEstadoSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=EstadoPedido.choices)


class EntregaSerializer(serializers.Serializer):
    pagos = PagoEntradaSerializer(many=True, allow_empty=False, max_length=4)
    efectivo_recibido = serializers.DecimalField(max_digits=12, decimal_places=2, required=False,
                                                 min_value=Decimal("0"), max_value=Decimal("9999999"))
