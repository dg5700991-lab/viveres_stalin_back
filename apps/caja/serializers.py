from decimal import Decimal

from rest_framework import serializers

from .models import MovimientoCaja, TipoMovCaja, Turno

DINERO = dict(max_digits=12, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("9999999"))


class TurnoSerializer(serializers.ModelSerializer):
    cajero_nombre = serializers.CharField(source="cajero.username", read_only=True)

    class Meta:
        model = Turno
        fields = ["id", "cajero_nombre", "estado", "creado_en", "cerrado_en", "fondo_inicial",
                  "esperado_efectivo", "esperado_transferencia", "contado_efectivo", "contado_transferencia",
                  "diferencia_efectivo", "diferencia_transferencia", "notas_cierre"]


class AperturaSerializer(serializers.Serializer):
    fondo_inicial = serializers.DecimalField(**DINERO)


class CierreSerializer(serializers.Serializer):
    contado_efectivo = serializers.DecimalField(**DINERO)
    contado_transferencia = serializers.DecimalField(**DINERO)
    notas = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class MovimientoCajaSerializer(serializers.ModelSerializer):
    tipo = serializers.ChoiceField(choices=TipoMovCaja.choices)
    monto = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))

    class Meta:
        model = MovimientoCaja
        fields = ["id", "creado_en", "tipo", "monto", "motivo"]
        read_only_fields = ["id", "creado_en"]
