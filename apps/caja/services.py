from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.clientes.models import MovimientoFiado, TipoFiado
from apps.core.auditoria import auditar
from apps.core.constantes import MetodoPago
from apps.usuarios.models import Rol
from apps.ventas.models import EstadoVenta, Pago

from .models import EstadoTurno, MovimientoCaja, TipoMovCaja, Turno

CERO = Decimal("0.00")


def exigir_turno(usuario):
    turno = Turno.objects.filter(cajero=usuario, estado=EstadoTurno.ABIERTO).first()
    if not turno:
        raise ValidationError({"turno": "Debe abrir un turno de caja antes de cobrar."})
    return turno


@transaction.atomic
def abrir_turno(*, usuario, fondo_inicial):
    if Turno.objects.filter(cajero=usuario, estado=EstadoTurno.ABIERTO).exists():
        raise ValidationError({"turno": "Ya tiene un turno abierto."})
    t = Turno.objects.create(cajero=usuario, fondo_inicial=fondo_inicial)
    auditar(usuario, "TURNO_ABIERTO", "Turno", t.id, {"fondo_inicial": fondo_inicial})
    return t


def _suma(qs):
    return qs.aggregate(s=Sum("monto"))["s"] or CERO


def calcular_cuadre(turno):
    """Lo que DEBERÍA haber al cierre, por método de pago."""
    pagos = Pago.objects.filter(venta__turno=turno, venta__estado=EstadoVenta.COMPLETADA)
    abonos = MovimientoFiado.objects.filter(turno=turno, tipo=TipoFiado.ABONO)
    movs = MovimientoCaja.objects.filter(turno=turno)
    ventas_ef = _suma(pagos.filter(metodo=MetodoPago.EFECTIVO))
    ventas_tr = _suma(pagos.filter(metodo=MetodoPago.TRANSFERENCIA))
    ab_ef = _suma(abonos.filter(metodo_pago=MetodoPago.EFECTIVO))
    ab_tr = _suma(abonos.filter(metodo_pago=MetodoPago.TRANSFERENCIA))
    ingresos = _suma(movs.filter(tipo=TipoMovCaja.INGRESO))
    egresos = _suma(movs.filter(tipo=TipoMovCaja.EGRESO))
    return {
        "fondo_inicial": turno.fondo_inicial,
        "ventas_efectivo": ventas_ef,
        "ventas_transferencia": ventas_tr,
        "ventas_fiado": _suma(pagos.filter(metodo=MetodoPago.FIADO)),  # informativo: no entra a caja
        "abonos_efectivo": ab_ef,
        "abonos_transferencia": ab_tr,
        "ingresos_caja": ingresos,
        "egresos_caja": egresos,
        "esperado_efectivo": turno.fondo_inicial + ventas_ef + ab_ef + ingresos - egresos,
        "esperado_transferencia": ventas_tr + ab_tr,
        "num_ventas": turno.ventas.filter(estado=EstadoVenta.COMPLETADA).count(),
    }


@transaction.atomic
def registrar_movimiento_caja(*, usuario, tipo, monto, motivo):
    turno = exigir_turno(usuario)
    mov = MovimientoCaja.objects.create(turno=turno, tipo=tipo, monto=monto, motivo=motivo, usuario=usuario)
    auditar(usuario, "MOVIMIENTO_CAJA", "Turno", turno.id, {"tipo": tipo, "monto": monto, "motivo": motivo})
    return mov


@transaction.atomic
def cerrar_turno(*, turno_id, usuario, contado_efectivo, contado_transferencia, notas=""):
    turno = Turno.objects.select_for_update().get(pk=turno_id)
    if turno.estado != EstadoTurno.ABIERTO:
        raise ValidationError({"turno": "El turno ya está cerrado."})
    if turno.cajero_id != usuario.id and usuario.rol != Rol.ADMIN:
        raise PermissionDenied("Solo el cajero del turno o un administrador puede cerrarlo.")
    c = calcular_cuadre(turno)
    turno.esperado_efectivo, turno.esperado_transferencia = c["esperado_efectivo"], c["esperado_transferencia"]
    turno.contado_efectivo, turno.contado_transferencia = contado_efectivo, contado_transferencia
    turno.diferencia_efectivo = contado_efectivo - c["esperado_efectivo"]          # <0 falta, >0 sobra
    turno.diferencia_transferencia = contado_transferencia - c["esperado_transferencia"]
    turno.notas_cierre, turno.estado, turno.cerrado_en = notas, EstadoTurno.CERRADO, timezone.now()
    turno.save()
    auditar(usuario, "TURNO_CERRADO", "Turno", turno.id,
            {"dif_efectivo": turno.diferencia_efectivo, "dif_transferencia": turno.diferencia_transferencia})
    return turno, c
