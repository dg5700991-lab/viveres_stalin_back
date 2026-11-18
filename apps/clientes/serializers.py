from decimal import Decimal

from rest_framework import serializers

from apps.core.constantes import MetodoPago
from apps.usuarios.models import Rol

from .models import Cliente, MovimientoFiado


class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = ["id", "nombre", "apellidos", "email", "telefono", "documento", "limite_credito", "saldo_fiado", "notas", "activo"]
        read_only_fields = ["saldo_fiado"]

    def validate_limite_credito(self, v):
        if self.context["request"].user.rol != Rol.ADMIN:
            raise serializers.ValidationError("Solo el administrador define el límite de crédito.")
        return v

    def validate_telefono(self, v):
        v = v.strip()
        qs = Cliente.objects.filter(telefono=v) if v else Cliente.objects.none()
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un cliente con ese teléfono.")
        return v


class MovimientoFiadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovimientoFiado
        fields = ["id", "creado_en", "tipo", "monto", "saldo_resultante", "metodo_pago", "referencia", "venta"]


class AbonoSerializer(serializers.Serializer):
    monto = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    metodo = serializers.ChoiceField(choices=[MetodoPago.EFECTIVO, MetodoPago.TRANSFERENCIA])
    referencia = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
