from decimal import Decimal

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalogo.models import Producto
from apps.core.auditoria import auditar

from .models import MovimientoInventario, TipoMovimiento


def _mover(p, *, tipo, cantidad, usuario, motivo="", costo_unitario=None, venta=None):
    """`p` debe venir bloqueado (select_for_update) dentro de una transacción."""
    nuevo = p.stock_actual + cantidad
    if nuevo < 0 and not settings.STOCK_NEGATIVO_PERMITIDO:
        raise ValidationError({"stock": f"Stock insuficiente de «{p.nombre}» (disponible: {p.stock_actual})."})
    p.stock_actual = nuevo
    p.save(update_fields=["stock_actual", "actualizado_en"])
    return MovimientoInventario.objects.create(
        producto=p, tipo=tipo, cantidad=cantidad, stock_resultante=nuevo, costo_unitario=costo_unitario,
        motivo=motivo[:200], usuario=usuario, venta=venta)


@transaction.atomic
def mover_stock(*, producto_id, tipo, cantidad, usuario, motivo="", venta=None):
    p = Producto.objects.select_for_update().get(pk=producto_id)
    return _mover(p, tipo=tipo, cantidad=cantidad, usuario=usuario, motivo=motivo, venta=venta)


@transaction.atomic
def registrar_entrada(*, producto_id, cantidad, usuario, costo_unitario=None, motivo="Compra / reposición"):
    p = Producto.objects.select_for_update().get(pk=producto_id)
    mov = _mover(p, tipo=TipoMovimiento.ENTRADA, cantidad=cantidad, usuario=usuario,
                 motivo=motivo, costo_unitario=costo_unitario)
    if costo_unitario is not None:
        p.costo = costo_unitario
        p.save(update_fields=["costo", "actualizado_en"])
    auditar(usuario, "ENTRADA_STOCK", "Producto", p.id, {"cantidad": cantidad, "costo": costo_unitario})
    return mov


@transaction.atomic
def ajustar_stock(*, producto_id, stock_real, usuario, motivo):
    """Conteo físico: fija el stock real y deja constancia de la diferencia (positiva o negativa)."""
    p = Producto.objects.select_for_update().get(pk=producto_id)
    delta = Decimal(stock_real) - p.stock_actual
    if delta == 0:
        return None
    mov = _mover(p, tipo=TipoMovimiento.AJUSTE, cantidad=delta, usuario=usuario, motivo=motivo)
    auditar(usuario, "AJUSTE_STOCK", "Producto", p.id, {"diferencia": delta, "motivo": motivo})
    return mov
