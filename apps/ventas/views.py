from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import EsAdmin, EsPersonal
from apps.core.utils import parse_fecha, parse_uuid
from apps.usuarios.models import Rol

from apps.catalogo.services import resolver_items

from .models import Venta
from .serializers import (
    AnulacionSerializer,
    CotizacionRequestSerializer,
    VentaCrearSerializer,
    VentaSerializer,
)
from .services import anular_venta, crear_venta


class VentaViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                   viewsets.GenericViewSet):
    """Sin PUT/PATCH/DELETE: una venta registrada solo puede anularse (con motivo y rastro)."""
    permission_classes = [EsPersonal]
    serializer_class = VentaSerializer

    def get_permissions(self):
        return [EsAdmin()] if self.action == "anular" else [EsPersonal()]

    def get_queryset(self):
        p = self.request.query_params
        qs = (Venta.objects.select_related("cajero", "cliente")
              .prefetch_related("detalles", "pagos"))
        if self.request.user.rol != Rol.ADMIN:
            qs = qs.filter(cajero=self.request.user)
        if p.get("turno"):
            qs = qs.filter(turno_id=parse_uuid(p["turno"], "turno"))
        if p.get("desde"):
            qs = qs.filter(creado_en__date__gte=parse_fecha(p["desde"], "desde"))
        if p.get("hasta"):
            qs = qs.filter(creado_en__date__lte=parse_fecha(p["hasta"], "hasta"))
        return qs

    def create(self, request, *args, **kwargs):
        s = VentaCrearSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        venta, creada = crear_venta(
            usuario=request.user, items=d["items"], pagos=d["pagos"], idempotency_key=d["idempotency_key"],
            cliente_id=d.get("cliente"), efectivo_recibido=d.get("efectivo_recibido"),
            nombre_fiado=d.get("nombre_fiado", ""))
        data = VentaSerializer(venta).data
        if getattr(venta, "vuelto", None) is not None:
            data["vuelto"] = venta.vuelto
        return Response(data, status=status.HTTP_201_CREATED if creada else status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="calcular-cobro")
    def calcular_cobro(self, request):
        """Calcula el total a cobrar detallado y el vuelto según el efectivo entregado por el cliente."""
        s = CotizacionRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        lineas = resolver_items(d["items"])
        total = sum((sub for _, _, sub in lineas), 0)
        items_resp = []
        for p, c, sub in lineas:
            items_resp.append({
                "producto_id": str(p.id),
                "nombre": p.nombre,
                "cantidad": c,
                "unidad_medida": p.unidad_medida,
                "precio_unitario": p.precio_venta,
                "subtotal": sub
            })
        efectivo = d.get("efectivo_recibido")
        vuelto = None
        falta = None
        if efectivo is not None:
            if efectivo >= total:
                vuelto = efectivo - total
                falta = 0
            else:
                vuelto = 0
                falta = total - efectivo

        return Response({
            "items": items_resp,
            "total_a_cobrar": total,
            "efectivo_recibido": efectivo,
            "vuelto_a_entregar": vuelto,
            "monto_faltante": falta,
            "puede_completarse": (efectivo >= total) if efectivo is not None else True
        })

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        venta = self.get_object()
        s = AnulacionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        venta = anular_venta(venta_id=venta.id, usuario=request.user, motivo=s.validated_data["motivo"])
        return Response(VentaSerializer(venta).data)
