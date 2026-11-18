from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.core.permissions import EsCliente, EsPersonal
from apps.ventas.serializers import VentaSerializer
from apps.usuarios.models import Rol

from .models import EstadoPedido, Pedido
from .serializers import (CambioEstadoSerializer, EntregaSerializer, PedidoCrearSerializer, PedidoSerializer)
from .services import acusar_pedido, cambiar_estado, crear_pedido, entregar_pedido


class PedidoViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                    viewsets.GenericViewSet):
    serializer_class = PedidoSerializer

    def get_permissions(self):
        if self.action == "create":
            return [EsCliente()]
        if self.action in ("estado", "acusar", "entregar", "alarma"):
            return [EsPersonal()]
        return [IsAuthenticated()]  # listar / ver / cancelar: cada rol ve solo lo suyo (get_queryset)

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "pedidos"
            return [ScopedRateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        qs = Pedido.objects.select_related("cliente").prefetch_related("detalles")
        user = self.request.user
        if user.rol == Rol.CLIENTE:  # protección a nivel de objeto: otro cliente recibe 404
            return qs.filter(cliente__usuario=user)
        estado = self.request.query_params.get("estado")
        return qs.filter(estado=estado) if estado in EstadoPedido.values else qs

    def create(self, request, *args, **kwargs):
        cliente = getattr(request.user, "cliente", None)
        if cliente is None or not cliente.activo:
            return Response({"detail": "Su usuario no está vinculado a un cliente activo."},
                            status=status.HTTP_403_FORBIDDEN)
        s = PedidoCrearSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        pedido = crear_pedido(cliente=cliente, items=d["items"], notas=d["notas"],
                              hora_estimada=d.get("hora_estimada_recogida"))
        return Response(PedidoSerializer(pedido).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None):
        p = self.get_object()
        cliente = getattr(request.user, "cliente", None) if request.user.rol == Rol.CLIENTE else None
        p = cambiar_estado(pedido_id=p.id, nuevo=EstadoPedido.CANCELADO, usuario=request.user,
                           cliente=cliente) if cliente else cambiar_estado(
            pedido_id=p.id, nuevo=EstadoPedido.CANCELADO, usuario=request.user)
        return Response(PedidoSerializer(p).data)

    @action(detail=False, methods=["get"])
    def alarma(self, request):
        """La pantalla de caja consulta esto cada ~5 s: suena/parpadea mientras `hay_alarma` sea true.
        Aprovechamos la llamada para auto-cancelar pedidos que llevan más de 1 hora sin ser retirados."""
        from django.utils import timezone
        from datetime import timedelta
        limite = timezone.now() - timedelta(hours=1)
        cancelados = Pedido.objects.filter(
            estado__in=[EstadoPedido.PENDIENTE, EstadoPedido.EN_PREPARACION],
            creado_en__lt=limite,
        ).update(estado=EstadoPedido.CANCELADO, alarma_pendiente=False)

        nuevos = self.get_queryset().filter(alarma_pendiente=True, estado=EstadoPedido.PENDIENTE)
        return Response({"hay_alarma": nuevos.exists(), "cantidad": nuevos.count(),
                         "pedidos": PedidoSerializer(nuevos[:20], many=True).data,
                         "cancelados_expirados": cancelados})

    @action(detail=True, methods=["post"])
    def acusar(self, request, pk=None):
        p = acusar_pedido(pedido_id=self.get_object().id, usuario=request.user)
        return Response(PedidoSerializer(p).data)

    @action(detail=True, methods=["post"])
    def estado(self, request, pk=None):
        s = CambioEstadoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        p = cambiar_estado(pedido_id=self.get_object().id, nuevo=s.validated_data["estado"], usuario=request.user)
        return Response(PedidoSerializer(p).data)

    @action(detail=True, methods=["post"])
    def entregar(self, request, pk=None):
        s = EntregaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        pedido, venta, creada = entregar_pedido(
            pedido_id=self.get_object().id, usuario=request.user, pagos=s.validated_data["pagos"],
            efectivo_recibido=s.validated_data.get("efectivo_recibido"))
        data = {"pedido": PedidoSerializer(pedido).data, "venta": VentaSerializer(venta).data}
        if getattr(venta, "vuelto", None) is not None:
            data["vuelto"] = venta.vuelto
        return Response(data, status=status.HTTP_201_CREATED if creada else status.HTTP_200_OK)
