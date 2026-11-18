import uuid
from decimal import Decimal as D

from django.db.models import Sum
from django.test import override_settings

from apps.catalogo.models import Producto, TipoProducto
from apps.inventario.models import MovimientoInventario, TipoMovimiento

from .base import Base


class InventarioTests(Base):
    def test_la_venta_descuenta_stock_y_deja_movimiento(self):
        self.abrir_turno()
        r = self.vender(self.items((self.chicle, 4), (self.arroz, "2.5")), [self.ef("4.00")])
        self.assertEqual(r.status_code, 201, r.content)
        self.refrescar(self.chicle, self.arroz)
        self.assertEqual(self.chicle.stock_actual, D("96"))
        self.assertEqual(self.arroz.stock_actual, D("47.5"))
        mov = MovimientoInventario.objects.get(producto=self.chicle)
        self.assertEqual((mov.tipo, mov.cantidad, mov.stock_resultante),
                         (TipoMovimiento.SALIDA_VENTA, D("-4"), D("96")))

    def test_renglones_repetidos_se_consolidan(self):
        self.abrir_turno()
        self.vender(self.items((self.chicle, 1), (self.chicle, 2)), [self.ef("1.50")])
        self.refrescar(self.chicle)
        self.assertEqual(self.chicle.stock_actual, D("97"))
        self.assertEqual(MovimientoInventario.objects.filter(producto=self.chicle).count(), 1)

    def test_doble_envio_no_cobra_ni_descuenta_dos_veces(self):
        self.abrir_turno()
        k = uuid.uuid4()
        r1 = self.vender(self.items((self.chicle, 2)), [self.ef("1.00")], key=k)
        r2 = self.vender(self.items((self.chicle, 2)), [self.ef("1.00")], key=k)
        self.assertEqual((r1.status_code, r2.status_code), (201, 200))
        self.assertEqual(r1.data["id"], r2.data["id"])
        self.refrescar(self.chicle)
        self.assertEqual(self.chicle.stock_actual, D("98"))

    def test_producto_por_unidad_no_admite_decimales(self):
        self.abrir_turno()
        r = self.vender(self.items((self.chicle, "1.5")), [self.ef("0.75")])
        self.assertEqual(r.status_code, 400)

    @override_settings(STOCK_NEGATIVO_PERMITIDO=False)
    def test_stock_insuficiente_revierte_toda_la_venta(self):
        self.abrir_turno()
        r = self.vender(self.items((self.arroz, 2), (self.chicle, 500)), [self.ef("251.60")])
        self.assertEqual(r.status_code, 400)
        self.refrescar(self.chicle, self.arroz)
        self.assertEqual((self.chicle.stock_actual, self.arroz.stock_actual), (D("100"), D("50")))
        self.assertEqual(MovimientoInventario.objects.count(), 0)

    def test_stock_negativo_permitido_no_frena_el_mostrador(self):
        self.abrir_turno()
        r = self.vender(self.items((self.chicle, 120)), [self.ef("60.00")])
        self.assertEqual(r.status_code, 201)
        self.refrescar(self.chicle)
        self.assertEqual(self.chicle.stock_actual, D("-20"))

    def test_anular_venta_devuelve_el_stock(self):
        self.abrir_turno()
        venta = self.vender(self.items((self.chicle, 10)), [self.ef("5.00")]).data
        self.como(self.cajero)
        self.assertEqual(self.client.post(f"/api/ventas/{venta['id']}/anular/", {"motivo": "x"}).status_code, 403)
        self.como(self.admin)
        r = self.client.post(f"/api/ventas/{venta['id']}/anular/", {"motivo": "Error de cobro"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.refrescar(self.chicle)
        self.assertEqual(self.chicle.stock_actual, D("100"))
        self.assertEqual(self.client.post(f"/api/ventas/{venta['id']}/anular/", {"motivo": "otra"},
                                          format="json").status_code, 400)

    def test_entrada_y_ajuste_por_conteo(self):
        nuevo = Producto.objects.create(tipo=TipoProducto.CODIGO, nombre="Galleta", codigo_barras="123456789",
                                        precio_venta=D("1.00"), stock_actual=D("0"))
        self.como(self.admin)
        r = self.client.post("/api/inventario/entradas/", {"producto": str(nuevo.id), "cantidad": "30",
                                                          "costo_unitario": "0.60"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.abrir_turno()
        self.vender(self.items((nuevo, 4)), [self.ef("4.00")])
        self.como(self.admin)
        r = self.client.post("/api/inventario/ajustes/", {"producto": str(nuevo.id), "stock_real": "24",
                                                         "motivo": "Conteo físico"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(D(r.data["cantidad"]), D("-2"))
        nuevo.refresh_from_db()
        self.assertEqual(nuevo.stock_actual, D("24"))
        # El libro de movimientos explica el 100% del stock:
        total = MovimientoInventario.objects.filter(producto=nuevo).aggregate(s=Sum("cantidad"))["s"]
        self.assertEqual(total, nuevo.stock_actual)
        self.assertEqual(nuevo.costo, D("0.60"))

    def test_ajuste_exige_admin_y_alertas_de_stock_bajo(self):
        self.chicle.stock_actual = D("3")
        self.chicle.save()
        self.como(self.cajero)
        self.assertEqual(self.client.post("/api/inventario/ajustes/", {
            "producto": str(self.chicle.id), "stock_real": "1", "motivo": "x"}, format="json").status_code, 403)
        r = self.client.get("/api/inventario/alertas/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([p["nombre"] for p in r.data["productos"]], ["Chicle"])
        self.assertNotIn("costo", r.data["productos"][0])
