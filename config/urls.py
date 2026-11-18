from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.caja.views import TurnoViewSet
from apps.catalogo.views import CategoriaViewSet, ProductoViewSet
from apps.clientes.views import ClienteViewSet, MiCuentaView
from apps.inventario.views import AjusteView, AlertasView, EntradaView, MovimientoViewSet
from apps.pedidos.views import PedidoViewSet
from apps.usuarios.views import LoginView, LogoutView, RefreshView, RegistroView, UsuarioViewSet
from apps.ventas.views import VentaViewSet

router = SimpleRouter()
router.register("categorias", CategoriaViewSet, basename="categoria")
router.register("productos", ProductoViewSet, basename="producto")
router.register("clientes", ClienteViewSet, basename="cliente")
router.register("usuarios", UsuarioViewSet, basename="usuario")
router.register("caja/turnos", TurnoViewSet, basename="turno")
router.register("ventas", VentaViewSet, basename="venta")
router.register("pedidos", PedidoViewSet, basename="pedido")
router.register("inventario/movimientos", MovimientoViewSet, basename="movimiento")

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/auth/login/", LoginView.as_view()),
    path("api/auth/refresh/", RefreshView.as_view()),
    path("api/auth/logout/", LogoutView.as_view()),
    path("api/auth/registro/", RegistroView.as_view()),
    path("api/inventario/entradas/", EntradaView.as_view()),
    path("api/inventario/ajustes/", AjusteView.as_view()),
    path("api/inventario/alertas/", AlertasView.as_view()),
    path("api/mi-cuenta/", MiCuentaView.as_view()),
    path("api/", include(router.urls)),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

