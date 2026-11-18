from django.db.models import F, Q
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.auditoria import auditar
from apps.core.permissions import EsAdmin, EsPersonal
from apps.usuarios.models import Rol

from .models import Categoria, Producto, TipoProducto
from .serializers import CategoriaSerializer, ProductoSerializer

SI = ("1", "true", "si")


class CategoriaViewSet(viewsets.ModelViewSet):
    queryset = Categoria.objects.all().order_by("nombre")
    serializer_class = CategoriaSerializer

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update", "destroy"):
            return [EsAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.user.rol == Rol.CLIENTE:
            return qs.filter(activo=True)
        return qs


class ProductoViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                      mixins.ListModelMixin, viewsets.GenericViewSet):
    """Sin DELETE: los productos se desactivan (`activo=false`) para conservar el historial."""
    serializer_class = ProductoSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]  # multipart = subida de imagen

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update"):
            return [EsAdmin()]
        if self.action == "por_codigo":
            return [EsPersonal()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user, p = self.request.user, self.request.query_params
        qs = Producto.objects.all().order_by("nombre")
        if user.rol == Rol.CLIENTE:
            return qs.filter(activo=True)
        if self.action == "list" and not (user.rol == Rol.ADMIN and p.get("incluir_inactivos") in SI):
            qs = qs.filter(activo=True)
        q = (p.get("q") or "").strip()[:60]
        if q:  # parámetros siempre vía ORM (consultas parametrizadas): sin SQL injection posible
            qs = qs.filter(Q(nombre__icontains=q) | Q(codigo_barras=q))
        if p.get("tipo") in TipoProducto.values:
            qs = qs.filter(tipo=p["tipo"])
        if p.get("stock_bajo") in SI:
            qs = qs.filter(stock_actual__lte=F("stock_minimo"))
        return qs

    @action(detail=False, methods=["get"], url_path=r"por-codigo/(?P<codigo>[A-Za-z0-9\-]{4,32})")
    def por_codigo(self, request, codigo):
        """Para el lector de barras: devuelve el producto exacto o 404 (para ofrecer 'registrar nuevo')."""
        p = Producto.objects.filter(codigo_barras=codigo, activo=True).first()
        if not p:
            raise NotFound("No existe un producto con ese código.")
        return Response(self.get_serializer(p).data)

    def perform_create(self, serializer):
        p = serializer.save()
        auditar(self.request.user, "PRODUCTO_CREADO", "Producto", p.id,
                {"nombre": p.nombre, "precio": p.precio_venta})

    def perform_update(self, serializer):
        antes = serializer.instance.precio_venta
        p = serializer.save()
        if p.precio_venta != antes:
            auditar(self.request.user, "PRECIO_CAMBIADO", "Producto", p.id,
                    {"antes": antes, "despues": p.precio_venta})
