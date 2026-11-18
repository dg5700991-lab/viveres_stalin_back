"""
Panel de administración de Django. Regla de oro: lo que tiene libro contable NO se edita aquí
(stock, saldos, ventas, turnos cerrados): solo se consulta. Los cambios pasan por la API/servicios.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from apps.caja.models import MovimientoCaja, Turno
from apps.catalogo.models import Categoria, Producto
from apps.clientes.models import Cliente, MovimientoFiado
from apps.inventario.models import MovimientoInventario
from apps.pedidos.models import Pedido
from apps.usuarios.models import Usuario
from apps.ventas.models import Venta

from .models import AuditLog


class SoloLectura(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Rol", {"fields": ("rol",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Rol", {"fields": ("rol",)}),)
    list_display = ("username", "rol", "is_active")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "descripcion", "activo")
    search_fields = ("nombre",)
    list_filter = ("activo",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "categoria", "tipo", "codigo_barras", "precio_venta", "stock_actual", "activo")
    search_fields = ("nombre", "codigo_barras")
    list_filter = ("categoria", "tipo", "activo")
    readonly_fields = ("stock_actual",)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "telefono", "saldo_fiado", "limite_credito", "activo")
    search_fields = ("nombre", "telefono")
    readonly_fields = ("saldo_fiado",)

    def has_delete_permission(self, request, obj=None):
        return False


for _modelo in (MovimientoInventario, MovimientoFiado, MovimientoCaja, AuditLog, Venta, Turno, Pedido):
    admin.site.register(_modelo, SoloLectura)
