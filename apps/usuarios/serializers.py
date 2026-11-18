from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.clientes.models import Cliente

from .models import Rol, Usuario


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data["rol"] = self.user.rol
        data["nombre"] = self.user.get_full_name() or self.user.username
        return data


class RegistroSerializer(serializers.Serializer):
    username = serializers.RegexField(r"^[A-Za-z0-9_.-]{4,30}$", max_length=30)
    password = serializers.CharField(write_only=True, max_length=128)
    nombre = serializers.CharField(max_length=120)
    apellidos = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    telefono = serializers.RegexField(r"^[0-9+]{7,15}$", max_length=15, required=False, allow_blank=True, default="")

    def validate_username(self, v):
        if Usuario.objects.filter(username__iexact=v).exists():
            raise serializers.ValidationError("Nombre de usuario no disponible.")
        return v

    def validate_telefono(self, v):
        if not v:
            return v
        if Cliente.objects.filter(telefono=v).exists():
            raise serializers.ValidationError("Ese telefono ya esta registrado.")
        return v

    def validate(self, attrs):
        validate_password(attrs["password"], user=Usuario(username=attrs["username"]))
        return attrs

    @transaction.atomic
    def create(self, datos):
        user = Usuario.objects.create_user(
            username=datos["username"],
            password=datos["password"],
            first_name=datos["nombre"][:150],
            last_name=datos.get("apellidos", "")[:150],
            email=datos.get("email", ""),
            rol=Rol.CLIENTE,
        )
        Cliente.objects.create(
            usuario=user,
            nombre=datos["nombre"],
            apellidos=datos.get("apellidos", ""),
            email=datos.get("email", ""),
            telefono=datos.get("telefono", ""),
        )
        return user


class UsuarioSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="first_name", required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, required=False, max_length=128)
    telefono = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Usuario
        fields = ["id", "username", "nombre", "email", "rol", "is_active", "date_joined", "password", "telefono"]
        read_only_fields = ["date_joined"]

    def create(self, validated_data):
        pwd = validated_data.pop("password", None)
        nombre = validated_data.pop("first_name", "")
        telefono = validated_data.pop("telefono", "")
        if not pwd:
            raise serializers.ValidationError({"password": "La contrasena es requerida."})
        user = Usuario.objects.create_user(
            username=validated_data["username"],
            password=pwd,
            email=validated_data.get("email", ""),
            first_name=nombre,
            rol=validated_data.get("rol", Rol.CAJERO),
            is_active=validated_data.get("is_active", True),
        )
        if user.rol == Rol.CLIENTE:
            Cliente.objects.create(usuario=user, nombre=nombre or user.username, telefono=telefono or "")
        return user

    def update(self, instance, validated_data):
        pwd = validated_data.pop("password", None)
        if "first_name" in validated_data:
            instance.first_name = validated_data["first_name"]
        if "email" in validated_data:
            instance.email = validated_data["email"]
        if "rol" in validated_data:
            instance.rol = validated_data["rol"]
        if "is_active" in validated_data:
            instance.is_active = validated_data["is_active"]
        if pwd:
            instance.set_password(pwd)
        instance.save()
        return instance
