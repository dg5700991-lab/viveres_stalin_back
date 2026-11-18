from django.db.models import F
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogo.models import Producto
from apps.catalogo.serializers import ProductoSerializer
from apps.core.permissions import EsAdmin, EsPersonal
from apps.core.utils import parse_fecha, parse_uuid

from .models import MovimientoInventario, TipoMovimiento
from .serializers import AjusteSerializer, EntradaSerializer, MovimientoSerializer
from .services import ajustar_stock, registrar_entrada


class MovimientoViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Libro de entradas y salidas (solo lectura). Filtros: producto, tipo, desde, hasta."""
    permission_classes = [EsAdmin]
    serializer_class = MovimientoSerializer

    def get_queryset(self):
        p = self.request.query_params
        qs = MovimientoInventario.objects.select_related("producto", "usuario")
        if p.get("producto"):
            qs = qs.filter(producto_id=parse_uuid(p["producto"], "producto"))
        if p.get("tipo") in TipoMovimiento.values:
            qs = qs.filter(tipo=p["tipo"])
        if p.get("desde"):
            qs = qs.filter(creado_en__date__gte=parse_fecha(p["desde"], "desde"))
        if p.get("hasta"):
            qs = qs.filter(creado_en__date__lte=parse_fecha(p["hasta"], "hasta"))
        return qs


class EntradaView(APIView):
    permission_classes = [EsAdmin]

    def post(self, request):
        s = EntradaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        mov = registrar_entrada(producto_id=d["producto"].id, cantidad=d["cantidad"], usuario=request.user,
                                costo_unitario=d.get("costo_unitario"),
                                motivo=d.get("motivo") or "Compra / reposición")
        return Response(MovimientoSerializer(mov).data, status=status.HTTP_201_CREATED)


class AjusteView(APIView):
    permission_classes = [EsAdmin]

    def post(self, request):
        s = AjusteSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        mov = ajustar_stock(producto_id=d["producto"].id, stock_real=d["stock_real"],
                            usuario=request.user, motivo=d["motivo"])
        if mov is None:
            return Response({"detail": "El stock ya coincide; no se registró ningún ajuste."})
        return Response(MovimientoSerializer(mov).data, status=status.HTTP_201_CREATED)


class AlertasView(APIView):
    """Productos activos con stock en o bajo el mínimo (incluye negativos = diferencias por corregir)."""
    permission_classes = [EsPersonal]

    def get(self, request):
        qs = Producto.objects.filter(activo=True, stock_actual__lte=F("stock_minimo")).order_by("stock_actual")
        return Response({"cantidad": qs.count(),
                         "productos": ProductoSerializer(qs[:200], many=True, context={"request": request}).data})
