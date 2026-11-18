from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.caja.services import exigir_turno
from apps.core.auditoria import auditar
from apps.core.constantes import MetodoPago

from .models import Cliente, MovimientoFiado, TipoFiado


def _bloquear(cliente_id):
    return Cliente.objects.select_for_update().get(pk=cliente_id)


@transaction.atomic
def registrar_cargo(*, cliente_id, monto, usuario, venta):
    c = _bloquear(cliente_id)
    if not c.activo:
        raise ValidationError({"cliente": "El cliente está inactivo."})
    nuevo = c.saldo_fiado + monto
    if c.limite_credito is not None and nuevo > c.limite_credito:
        raise ValidationError({"cliente": f"Supera el límite de crédito de {c.limite_credito}."})
    c.saldo_fiado = nuevo
    c.save(update_fields=["saldo_fiado", "actualizado_en"])
    return MovimientoFiado.objects.create(cliente=c, tipo=TipoFiado.CARGO, monto=monto, saldo_resultante=nuevo,
                                          venta=venta, turno=venta.turno, usuario=usuario)


@transaction.atomic
def registrar_reverso(*, cliente_id, monto, usuario, venta):
    c = _bloquear(cliente_id)
    if monto > c.saldo_fiado:
        raise ValidationError({"venta": "El cliente ya abonó a esta deuda: no se puede anular la venta. "
                                        "Registre la devolución del dinero por otra vía."})
    c.saldo_fiado -= monto
    c.save(update_fields=["saldo_fiado", "actualizado_en"])
    return MovimientoFiado.objects.create(cliente=c, tipo=TipoFiado.REVERSO, monto=monto,
                                          saldo_resultante=c.saldo_fiado, venta=venta,
                                          turno=venta.turno, usuario=usuario)


@transaction.atomic
def registrar_abono(*, cliente_id, monto, metodo, referencia="", usuario):
    turno = exigir_turno(usuario)  # el dinero entra a la caja de un turno concreto
    if metodo not in (MetodoPago.EFECTIVO, MetodoPago.TRANSFERENCIA):
        raise ValidationError({"metodo": "Un abono se paga en efectivo o transferencia."})
    if metodo == MetodoPago.TRANSFERENCIA and len(referencia.strip()) < 3:
        raise ValidationError({"referencia": "Ingrese el n.º de comprobante de la transferencia."})
    c = _bloquear(cliente_id)
    if monto > c.saldo_fiado:
        raise ValidationError({"monto": f"El abono excede la deuda actual ({c.saldo_fiado})."})
    c.saldo_fiado -= monto
    c.save(update_fields=["saldo_fiado", "actualizado_en"])
    mov = MovimientoFiado.objects.create(
        cliente=c, tipo=TipoFiado.ABONO, monto=monto, saldo_resultante=c.saldo_fiado, metodo_pago=metodo,
        referencia=referencia.strip(), turno=turno, usuario=usuario)
    auditar(usuario, "ABONO_FIADO", "Cliente", c.id, {"monto": monto, "metodo": metodo})
    return mov
