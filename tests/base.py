import uuid
from decimal import Decimal as D

from rest_framework.test import APITestCase

from apps.catalogo.models import Producto, TipoProducto, Unidad
from apps.clientes.models import Cliente
from apps.usuarios.models import Rol, Usuario

CLAVE = "Clave-Segura-123"


class Base(APITestCase):
    def setUp(self):
        mk = lambda u, r: Usuario.objects.create_user(u, password=CLAVE, rol=r)
        self.admin = mk("admin1", Rol.ADMIN)
        self.cajero = mk("cajero1", Rol.CAJERO)
        self.user_ana = mk("ana_user", Rol.CLIENTE)
        self.user_beto = mk("beto_user", Rol.CLIENTE)
        self.ana = Cliente.objects.create(usuario=self.user_ana, nombre="Ana", telefono="0991111111")
        self.beto = Cliente.objects.create(usuario=self.user_beto, nombre="Beto", telefono="0992222222")
        self.chicle = Producto.objects.create(
            tipo=TipoProducto.CODIGO, nombre="Chicle", codigo_barras="7861000000011",
            precio_venta=D("0.50"), costo=D("0.30"), stock_actual=D("100"), stock_minimo=D("10"))
        self.arroz = Producto.objects.create(
            tipo=TipoProducto.GRANEL, nombre="Arroz", unidad_medida=Unidad.LIBRA,
            precio_venta=D("0.80"), stock_actual=D("50"), stock_minimo=D("5"))

    # ---- ayudas
    def como(self, user):
        # Usuario fresco desde la BD, como en una petición real (evita relaciones cacheadas en memoria).
        self.client.force_authenticate(type(user).objects.get(pk=user.pk))

    def abrir_turno(self, user=None, fondo="50.00"):
        self.como(user or self.cajero)
        r = self.client.post("/api/caja/turnos/abrir/", {"fondo_inicial": fondo}, format="json")
        assert r.status_code == 201, r.content
        return r.data

    def items(self, *pares):
        return [{"producto": str(p.id), "cantidad": str(c)} for p, c in pares]

    def vender(self, items, pagos, cliente=None, key=None, **extra):
        body = {"items": items, "pagos": pagos, "idempotency_key": str(key or uuid.uuid4()), **extra}
        if cliente:
            body["cliente"] = str(cliente.id)
        return self.client.post("/api/ventas/", body, format="json")

    @staticmethod
    def ef(monto):
        return {"metodo": "EFECTIVO", "monto": str(monto)}

    @staticmethod
    def tr(monto, ref="TRX-1001"):
        return {"metodo": "TRANSFERENCIA", "monto": str(monto), "referencia": ref}

    @staticmethod
    def fi(monto):
        return {"metodo": "FIADO", "monto": str(monto)}

    def refrescar(self, *objs):
        for o in objs:
            o.refresh_from_db()
