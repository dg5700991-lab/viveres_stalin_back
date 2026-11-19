from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.core.permissions import EsAdmin, EsPersonal
from apps.usuarios.models import Rol

from .models import EstadoTurno, Turno, CarritoCaja
from .serializers import (AperturaSerializer, CierreSerializer, MovimientoCajaSerializer, TurnoSerializer)
from .services import (abrir_turno, calcular_cuadre, cerrar_turno, exigir_turno, registrar_movimiento_caja)


class TurnoViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [EsPersonal]
    serializer_class = TurnoSerializer

    def get_queryset(self):
        qs = Turno.objects.select_related("cajero")
        return qs if self.request.user.rol == Rol.ADMIN else qs.filter(cajero=self.request.user)

    @action(detail=False, methods=["post"])
    def abrir(self, request):
        s = AperturaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        t = abrir_turno(usuario=request.user, fondo_inicial=s.validated_data["fondo_inicial"])
        return Response(TurnoSerializer(t).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def actual(self, request):
        t = Turno.objects.filter(cajero=request.user, estado=EstadoTurno.ABIERTO).first()
        if not t:
            raise NotFound("No tiene un turno abierto.")
        data = {
            "turno": TurnoSerializer(t).data,
            "cuadre_parcial": calcular_cuadre(t),
        }
        return Response(data)

    @action(detail=False, methods=["post"])
    def cerrar(self, request):
        s = CierreSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        t = exigir_turno(request.user)
        turno, cuadre = cerrar_turno(
            turno_id=t.id,
            usuario=request.user,
            contado_efectivo=s.validated_data["contado_efectivo"],
            contado_transferencia=s.validated_data["contado_transferencia"],
            notas=s.validated_data.get("notas", ""),
        )
        return Response({"turno": TurnoSerializer(turno).data, "cuadre": cuadre})

    @action(detail=False, methods=["post"], url_path="movimientos")
    def movimiento(self, request):
        s = MovimientoCajaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        mov = registrar_movimiento_caja(usuario=request.user, **s.validated_data)
        return Response(MovimientoCajaSerializer(mov).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], permission_classes=[EsAdmin])
    def cuadre(self, request, pk=None):
        t = self.get_object()
        return Response({"turno": TurnoSerializer(t).data, "cuadre": calcular_cuadre(t)})

    @action(detail=False, methods=["get", "put", "post"], url_path="carrito")
    def carrito(self, request):
        obj, _ = CarritoCaja.objects.get_or_create(cajero=request.user)
        if request.method in ["PUT", "POST"]:
            items = request.data.get("items", [])
            if not isinstance(items, list):
                return Response({"detail": "items debe ser una lista"}, status=status.HTTP_400_BAD_REQUEST)
            obj.items = items
            obj.version = (obj.version or 0) + 1
            obj.save(update_fields=["items", "version", "actualizado_en"])
            return Response({"items": obj.items, "version": obj.version, "actualizado_en": obj.actualizado_en})

        return Response({"items": obj.items, "version": obj.version, "actualizado_en": obj.actualizado_en})

