from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.core.permissions import EsAdmin
from .models import Usuario
from .serializers import LoginSerializer, RegistroSerializer, UsuarioSerializer


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_scope = "login"
    throttle_classes = [ScopedRateThrottle]


class RefreshView(TokenRefreshView):
    pass


class LogoutView(APIView):
    """Invalida el refresh token (lista negra): cerrar sesion."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            RefreshToken(request.data.get("refresh", "")).blacklist()
        except TokenError:
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class RegistroView(APIView):
    """Auto-registro de clientes de la app (rol CLIENTE siempre; el personal lo crea el admin)."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "registro"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        s = RegistroSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        s.save()
        return Response({"detail": "Cuenta creada. Ya puede iniciar sesion."}, status=status.HTTP_201_CREATED)


class UsuarioViewSet(viewsets.ModelViewSet):
    """Gestion de usuarios por el administrador (crear cajeros, clientes, administradores)."""
    permission_classes = [EsAdmin]
    serializer_class = UsuarioSerializer
    queryset = Usuario.objects.all().order_by("-date_joined")

