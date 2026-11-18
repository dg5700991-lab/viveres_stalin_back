from decimal import Decimal

from django.db.models import Q, Sum
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import EsCliente, EsPersonal

from .models import Cliente
from .serializers import AbonoSerializer, ClienteSerializer, MovimientoFiadoSerializer
from .services import registrar_abono


class ClienteViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                     mixins.ListModelMixin, viewsets.GenericViewSet):
    """Sin DELETE: los clientes se desactivan, su libreta se conserva."""
    permission_classes = [EsPersonal]
    serializer_class = ClienteSerializer

    def get_queryset(self):
        qs = Cliente.objects.all()
        q = (self.request.query_params.get("q") or "").strip()[:60]
        if q:
            qs = qs.filter(Q(nombre__icontains=q) | Q(apellidos__icontains=q) | Q(telefono__icontains=q) | Q(documento=q) | Q(email__icontains=q))
        return qs

    @action(detail=False, methods=["get"])
    def deudores(self, request):
        """¿Quién debe y cuánto? Ordenado de mayor a menor deuda + total por cobrar."""
        qs = Cliente.objects.filter(saldo_fiado__gt=0).order_by("-saldo_fiado")
        total = qs.aggregate(t=Sum("saldo_fiado"))["t"] or Decimal("0.00")
        return Response({"total_por_cobrar": total, "clientes": ClienteSerializer(
            qs, many=True, context=self.get_serializer_context()).data})

    @action(detail=True, methods=["get"])
    def libreta(self, request, pk=None):
        c = self.get_object()
        movs = c.movimientos.all()[:200]
        return Response({"cliente": self.get_serializer(c).data, "saldo": c.saldo_fiado,
                         "movimientos": MovimientoFiadoSerializer(movs, many=True).data})

    @action(detail=True, methods=["post"])
    def abono(self, request, pk=None):
        c = self.get_object()
        s = AbonoSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        mov = registrar_abono(cliente_id=c.id, monto=d["monto"], metodo=d["metodo"],
                              referencia=d["referencia"], usuario=request.user)
        return Response(MovimientoFiadoSerializer(mov).data, status=status.HTTP_201_CREATED)


class MiCuentaView(APIView):
    """El cliente de la app ve SU propia libreta (nunca la de otros)."""
    permission_classes = [EsCliente]

    def get(self, request):
        c = getattr(request.user, "cliente", None)
        if c is None:
            raise NotFound("Su usuario no está vinculado a un cliente.")
        return Response({"nombre": c.nombre, "saldo": c.saldo_fiado, "limite_credito": c.limite_credito,
                         "movimientos": MovimientoFiadoSerializer(c.movimientos.all()[:100], many=True).data})
