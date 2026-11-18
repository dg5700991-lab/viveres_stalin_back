from rest_framework.permissions import BasePermission

from apps.usuarios.models import Rol


class _PorRol(BasePermission):
    roles = ()

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.is_active and u.rol in self.roles)


class EsAdmin(_PorRol):
    roles = (Rol.ADMIN,)


class EsPersonal(_PorRol):
    roles = (Rol.ADMIN, Rol.CAJERO)


class EsCliente(_PorRol):
    roles = (Rol.CLIENTE,)
