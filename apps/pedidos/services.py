from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.catalogo.services import resolver_items
from apps.core.auditoria import auditar
from apps.ventas.models import OrigenVenta
from apps.ventas.services import crear_venta

from .models import DetallePedido, EstadoPedido, Pedido

E = EstadoPedido
ACTIVOS = [E.PENDIENTE, E.EN_PREPARACION, E.LISTO]
MAX_ACTIVOS_POR_CLIENTE = 3
TRANSICIONES = {
    E.PENDIENTE: {E.EN_PREPARACION, E.CANCELADO},
    E.EN_PREPARACION: {E.LISTO, E.CANCELADO},
    E.LISTO: {E.CANCELADO},          # ENTREGADO solo ocurre cobrando (entregar_pedido)
    E.ENTREGADO: set(),
    E.CANCELADO: set(),
}


@transaction.atomic
def crear_pedido(*, cliente, items, notas="", hora_estimada=None):
    if Pedido.objects.filter(cliente=cliente, estado__in=ACTIVOS).count() >= MAX_ACTIVOS_POR_CLIENTE:
        raise ValidationError({"pedido": f"Ya tiene {MAX_ACTIVOS_POR_CLIENTE} pedidos activos."})
    lineas = resolver_items(items)
    total = sum((s for _, _, s in lineas), Decimal("0"))
    if total <= 0:
        raise ValidationError({"items": "El pedido debe tener un total mayor que cero."})
    pedido = Pedido.objects.create(cliente=cliente, notas=notas, hora_estimada_recogida=hora_estimada,
                                   total_estimado=total, alarma_pendiente=True)
    DetallePedido.objects.bulk_create([
        DetallePedido(pedido=pedido, producto=p, nombre_producto=p.nombre, cantidad=c,
                      precio_unitario=p.precio_venta, subtotal=s) for p, c, s in lineas])
    return pedido


@transaction.atomic
def cambiar_estado(*, pedido_id, nuevo, usuario, cliente=None):
    """`cliente` (si viene) restringe la acción: el cliente solo cancela SUS pedidos aún pendientes."""
    p = Pedido.objects.select_for_update().get(pk=pedido_id)
    if cliente is not None and (p.cliente_id != cliente.id or p.estado != E.PENDIENTE or nuevo != E.CANCELADO):
        raise ValidationError({"estado": "Solo puede cancelar un pedido que aún está pendiente."})
    if nuevo not in TRANSICIONES[p.estado]:
        raise ValidationError({"estado": f"No se puede pasar de {p.estado} a {nuevo}."})
    p.estado, p.alarma_pendiente = nuevo, False
    if cliente is None:
        p.atendido_por = usuario
    p.save()
    auditar(usuario, "PEDIDO_" + nuevo, "Pedido", p.id)
    return p


@transaction.atomic
def acusar_pedido(*, pedido_id, usuario):
    """El personal 'apaga' la alarma al ver el pedido."""
    p = Pedido.objects.select_for_update().get(pk=pedido_id)
    p.alarma_pendiente, p.atendido_por = False, usuario
    p.save(update_fields=["alarma_pendiente", "atendido_por", "actualizado_en"])
    return p


@transaction.atomic
def entregar_pedido(*, pedido_id, usuario, pagos, efectivo_recibido=None):
    """Cobra en tienda (precios vigentes), crea la venta, descuenta stock y cierra el pedido. Idempotente."""
    p = Pedido.objects.select_for_update().get(pk=pedido_id)
    if p.estado == E.ENTREGADO:
        return p, p.venta, False
    if p.estado == E.CANCELADO:
        raise ValidationError({"estado": "El pedido está cancelado."})
    items = [{"producto": d.producto_id, "cantidad": d.cantidad} for d in p.detalles.all()]
    venta, creada = crear_venta(usuario=usuario, items=items, pagos=pagos, idempotency_key=p.id,
                                cliente_id=p.cliente_id, origen=OrigenVenta.PEDIDO,
                                efectivo_recibido=efectivo_recibido)
    p.estado, p.venta, p.alarma_pendiente, p.atendido_por = E.ENTREGADO, venta, False, usuario
    p.save()
    auditar(usuario, "PEDIDO_ENTREGADO", "Pedido", p.id, {"venta": venta.id, "total": venta.total})
    return p, venta, creada
