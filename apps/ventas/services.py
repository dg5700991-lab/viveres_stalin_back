import logging
from decimal import Decimal

from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.caja.models import EstadoTurno
from apps.caja.services import exigir_turno
from apps.catalogo.services import resolver_items
from apps.clientes.models import Cliente
from apps.clientes.services import registrar_cargo, registrar_reverso
from apps.core.auditoria import auditar
from apps.core.constantes import MetodoPago
from apps.inventario.models import TipoMovimiento
from apps.inventario.services import mover_stock

from .models import DetalleVenta, EstadoVenta, OrigenVenta, Pago, Venta

logger = logging.getLogger(__name__)


def _validar_pagos(pagos, total, cliente_id, nombre_fiado):
    if sum((p["monto"] for p in pagos), Decimal("0")) != total:
        raise ValidationError({"pagos": f"Los pagos deben sumar exactamente el total ({total})."})
    for p in pagos:
        if p["metodo"] == MetodoPago.TRANSFERENCIA and len((p.get("referencia") or "").strip()) < 3:
            raise ValidationError({"pagos": "La transferencia debe confirmarse con el n.º de comprobante."})
        if p["metodo"] == MetodoPago.FIADO and not cliente_id and not (nombre_fiado or "").strip():
            raise ValidationError({"pagos": "Para vender a fiado selecciona un cliente o escribe el nombre del deudor."})


def _enviar_comprobante_email(venta):
    """Envía resumen de compra por email solo si el cliente registrado tiene correo."""
    try:
        if not (venta.cliente and venta.cliente.email):
            return
        cliente = venta.cliente
        detalles = venta.detalles.all()
        lineas = "\n".join(
            f"  {d.cantidad} x {d.nombre_producto} = ${d.subtotal}" for d in detalles
        )
        mensaje = (
            f"Hola {cliente.nombre},\n\n"
            f"Tu comprobante de compra en Víveres Stalin:\n\n"
            f"Ticket #{venta.id}\n"
            f"Fecha: {venta.creado_en.strftime('%d/%m/%Y %H:%M')}\n\n"
            f"Detalle:\n{lineas}\n\n"
            f"TOTAL: ${venta.total}\n\n"
            f"¡Gracias por tu compra en Víveres Stalin!\n"
        )
        send_mail(
            subject=f"Comprobante de compra #{venta.id} - Víveres Stalin",
            message=mensaje,
            from_email=None,  # usa DEFAULT_FROM_EMAIL de settings
            recipient_list=[cliente.email],
            fail_silently=True,
        )
    except Exception:
        logger.warning("No se pudo enviar email para venta %s", venta.id, exc_info=True)


def crear_venta(*, usuario, items, pagos, idempotency_key, cliente_id=None,
                origen=OrigenVenta.MOSTRADOR, efectivo_recibido=None, nombre_fiado=""):
    """Devuelve (venta, creada). Si la clave ya existe devuelve la venta original sin duplicar nada."""
    existente = Venta.objects.filter(idempotency_key=idempotency_key).first()
    if existente:
        return existente, False
    turno = exigir_turno(usuario)
    if cliente_id and not Cliente.objects.filter(pk=cliente_id, activo=True).exists():
        raise ValidationError({"cliente": "Cliente no encontrado o inactivo."})
    try:
        with transaction.atomic():
            lineas = resolver_items(items)
            total = sum((sub for _, _, sub in lineas), Decimal("0"))
            if total <= 0:
                raise ValidationError({"items": "El total de la venta debe ser mayor que cero."})
            _validar_pagos(pagos, total, cliente_id, nombre_fiado)
            vuelto = None
            if efectivo_recibido is not None:
                en_efectivo = sum((p["monto"] for p in pagos if p["metodo"] == MetodoPago.EFECTIVO), Decimal("0"))
                if efectivo_recibido < en_efectivo:
                    raise ValidationError({"efectivo_recibido": "Es menor que lo cobrado en efectivo."})
                vuelto = efectivo_recibido - en_efectivo

            venta = Venta.objects.create(
                idempotency_key=idempotency_key,
                turno=turno,
                cajero=usuario,
                cliente_id=cliente_id,
                origen=origen,
                total=total,
                nombre_fiado=(nombre_fiado or "").strip(),
            )
            DetalleVenta.objects.bulk_create([
                DetalleVenta(venta=venta, producto=p, nombre_producto=p.nombre, cantidad=c,
                             precio_unitario=p.precio_venta, subtotal=s) for p, c, s in lineas])
            Pago.objects.bulk_create([
                Pago(venta=venta, metodo=p["metodo"], monto=p["monto"],
                     referencia=(p.get("referencia") or "").strip()) for p in pagos])
            for p, c, _ in lineas:  # orden fijo por id → sin interbloqueos entre ventas simultáneas
                mover_stock(producto_id=p.id, tipo=TipoMovimiento.SALIDA_VENTA, cantidad=-c, usuario=usuario,
                            motivo=f"Venta #{venta.id}", venta=venta)
            for p in pagos:
                if p["metodo"] == MetodoPago.FIADO:
                    target_cliente_id = cliente_id
                    if not target_cliente_id and (nombre_fiado or "").strip():
                        c_obj, _ = Cliente.objects.get_or_create(
                            nombre=nombre_fiado.strip(),
                            defaults={"activo": True}
                        )
                        target_cliente_id = c_obj.id
                        if not venta.cliente_id:
                            venta.cliente = c_obj
                            venta.save(update_fields=["cliente"])
                    if target_cliente_id:
                        registrar_cargo(cliente_id=target_cliente_id, monto=p["monto"], usuario=usuario, venta=venta)
            auditar(usuario, "VENTA_CREADA", "Venta", venta.id, {"total": total, "origen": origen})
            venta.vuelto = vuelto
            # Enviar email al cliente registrado si tiene correo (nunca bloquea la venta)
            _enviar_comprobante_email(venta)
            return venta, True
    except IntegrityError:
        existente = Venta.objects.filter(idempotency_key=idempotency_key).first()
        if existente:  # doble envío simultáneo: gana la primera
            return existente, False
        raise


@transaction.atomic
def anular_venta(*, venta_id, usuario, motivo):
    """Solo mientras el turno de la venta siga abierto (así el cuadre no cambia de un turno a otro)."""
    venta = Venta.objects.select_for_update().select_related("turno").get(pk=venta_id)
    if venta.estado == EstadoVenta.ANULADA:
        raise ValidationError({"venta": "La venta ya está anulada."})
    if venta.turno.estado != EstadoTurno.ABIERTO:
        raise ValidationError({"venta": "El turno de esta venta ya cerró; no se puede anular."})
    for d in venta.detalles.all():
        mover_stock(producto_id=d.producto_id, tipo=TipoMovimiento.ANULACION_VENTA, cantidad=d.cantidad,
                    usuario=usuario, motivo=f"Anulación venta #{venta.id}", venta=venta)
    for p in venta.pagos.filter(metodo=MetodoPago.FIADO):
        registrar_reverso(cliente_id=venta.cliente_id, monto=p.monto, usuario=usuario, venta=venta)
    venta.estado, venta.anulada_en = EstadoVenta.ANULADA, timezone.now()
    venta.anulada_por, venta.motivo_anulacion = usuario, motivo[:200]
    venta.save(update_fields=["estado", "anulada_en", "anulada_por", "motivo_anulacion"])
    auditar(usuario, "VENTA_ANULADA", "Venta", venta.id, {"motivo": motivo, "total": venta.total})
    return venta
