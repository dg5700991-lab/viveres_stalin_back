from decimal import Decimal

from rest_framework import serializers

from apps.catalogo.models import Producto

from .models import MovimientoInventario


class MovimientoSerializer(serializers.ModelSerializer):
    producto_nombre = serializers.CharField(source="producto.nombre", read_only=True)
    usuario_nombre = serializers.CharField(source="usuario.username", read_only=True)

    class Meta:
        model = MovimientoInventario
        fields = ["id", "creado_en", "producto", "producto_nombre", "tipo", "cantidad", "stock_resultante",
                  "costo_unitario", "motivo", "usuario_nombre", "venta"]


class EntradaSerializer(serializers.Serializer):
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.filter(activo=True))
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"),
                                        max_value=Decimal("1000000"))
    costo_unitario = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"),
                                              required=False)
    motivo = serializers.CharField(max_length=200, required=False, allow_blank=True)


class AjusteSerializer(serializers.Serializer):
    producto = serializers.PrimaryKeyRelatedField(queryset=Producto.objects.all())
    stock_real = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0"))
    motivo = serializers.CharField(max_length=200)
