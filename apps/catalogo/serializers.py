from rest_framework import serializers

from apps.usuarios.models import Rol

from .imagenes import procesar_imagen
from .models import Categoria, Producto, TipoProducto


class CategoriaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Categoria
        fields = ["id", "nombre", "descripcion", "activo"]


class ProductoSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source="categoria.nombre", read_only=True, default=None)
    imagen = serializers.ImageField(write_only=True, required=False, allow_null=True)
    imagen_url = serializers.SerializerMethodField()
    stock_bajo = serializers.BooleanField(read_only=True)

    class Meta:
        model = Producto
        fields = ["id", "categoria", "categoria_nombre", "tipo", "nombre", "codigo_barras", "unidad_medida", "precio_venta", "costo",
                  "stock_actual", "stock_minimo", "stock_bajo", "imagen", "imagen_url", "activo"]
        read_only_fields = ["stock_actual"]  # el stock solo cambia por movimientos de inventario

    def get_imagen_url(self, obj):
        return obj.imagen.url if obj.imagen else None

    def validate_nombre(self, v):
        v = " ".join(v.split())
        if not v:
            raise serializers.ValidationError("Requerido.")
        return v

    def validate_codigo_barras(self, v):
        return (v or "").strip() or None

    def validate_imagen(self, v):
        return procesar_imagen(v) if v else None

    def validate(self, attrs):
        inst = self.instance
        if inst and "tipo" in attrs and attrs["tipo"] != inst.tipo:
            raise serializers.ValidationError({"tipo": "El tipo de producto no se puede cambiar."})
        tipo = attrs.get("tipo", inst.tipo if inst else None)
        codigo = attrs.get("codigo_barras", inst.codigo_barras if inst else None)
        if tipo == TipoProducto.GRANEL and codigo:
            raise serializers.ValidationError({"codigo_barras": "Los productos a granel no llevan código."})
        if tipo == TipoProducto.CODIGO and not codigo:
            raise serializers.ValidationError({"codigo_barras": "Este tipo de producto requiere código de barras."})
        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        rol = self.context["request"].user.rol
        if rol != Rol.ADMIN:
            data.pop("costo")  # el costo (margen) solo lo ve el administrador
        if rol == Rol.CLIENTE:
            for campo in ("stock_actual", "stock_minimo", "stock_bajo"):
                data.pop(campo)
            data["disponible"] = instance.stock_actual > 0
        return data
