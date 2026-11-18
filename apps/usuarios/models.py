import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class Rol(models.TextChoices):
    ADMIN = "ADMIN", "Administrador"
    CAJERO = "CAJERO", "Cajero"
    CLIENTE = "CLIENTE", "Cliente"


class Usuario(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rol = models.CharField(max_length=10, choices=Rol.choices, default=Rol.CLIENTE)

    @property
    def es_personal(self):
        return self.rol in (Rol.ADMIN, Rol.CAJERO)

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.rol = Rol.ADMIN
        super().save(*args, **kwargs)
