from decimal import ROUND_HALF_UP, Decimal

from rest_framework.exceptions import ValidationError

from .models import Producto, Unidad

CENTAVO = Decimal("0.01")


def resolver_items(items):
    """
    items: [{'producto': UUID, 'cantidad': Decimal}, ...]
    Devuelve [(Producto, cantidad, subtotal)] consolidado (un renglón por producto) y ordenado por id
    (el orden fijo evita bloqueos cruzados entre ventas simultáneas).
    """
    acumulado = {}
    for it in items:
        acumulado[it["producto"]] = acumulado.get(it["producto"], Decimal("0")) + it["cantidad"]
    productos = {p.id: p for p in Producto.objects.filter(id__in=list(acumulado), activo=True)}
    if set(acumulado) - set(productos):
        raise ValidationError({"items": "Hay productos que no existen o están inactivos."})
    resultado = []
    for pid in sorted(acumulado, key=str):
        p, cant = productos[pid], acumulado[pid]
        if p.unidad_medida == Unidad.UNIDAD and cant != cant.to_integral_value():
            raise ValidationError({"items": f"«{p.nombre}» se vende por unidades enteras."})
        subtotal = (p.precio_venta * cant).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        resultado.append((p, cant, subtotal))
    return resultado
