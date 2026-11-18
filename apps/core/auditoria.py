from .models import AuditLog


def auditar(usuario, accion, entidad, entidad_id, detalle=None):
    """Deja constancia (inmutable) de quién hizo qué: ventas, anulaciones, ajustes, precios, cierres."""
    AuditLog.objects.create(
        usuario=usuario if usuario is not None and getattr(usuario, "pk", None) else None,
        accion=accion, entidad=entidad, entidad_id=str(entidad_id), detalle=detalle or {},
    )
