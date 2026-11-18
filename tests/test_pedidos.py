from decimal import Decimal as D

from apps.ventas.models import Venta

from .base import Base


class PedidosTests(Base):
    def crear_pedido(self, user=None, items=None):
        self.como(user or self.user_ana)
        return self.client.post("/api/pedidos/", {
            "items": items or self.items((self.chicle, 4), (self.arroz, 2)), "notas": "Paso en 20 min"},
            format="json")

    def test_pedido_dispara_alarma_y_se_apaga_al_acusar(self):
        r = self.crear_pedido()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(D(r.data["total_estimado"]), D("3.60"))
        pid = r.data["id"]
        self.como(self.cajero)
        a = self.client.get("/api/pedidos/alarma/").data
        self.assertTrue(a["hay_alarma"])
        self.assertEqual(a["cantidad"], 1)
        self.assertEqual(self.client.post(f"/api/pedidos/{pid}/acusar/").status_code, 200)
        self.assertFalse(self.client.get("/api/pedidos/alarma/").data["hay_alarma"])

    def test_pedido_no_toca_stock_hasta_cobrar_en_tienda(self):
        self.crear_pedido()
        self.refrescar(self.chicle)
        self.assertEqual(self.chicle.stock_actual, D("100"))

    def test_entrega_cobra_crea_venta_descuenta_stock_y_es_idempotente(self):
        pid = self.crear_pedido().data["id"]
        self.abrir_turno()
        for estado in ("EN_PREPARACION", "LISTO"):
            self.assertEqual(self.client.post(f"/api/pedidos/{pid}/estado/", {"estado": estado},
                                              format="json").status_code, 200)
        pago = {"pagos": [self.ef("3.60")], "efectivo_recibido": "5.00"}
        r = self.client.post(f"/api/pedidos/{pid}/entregar/", pago, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(D(r.data["vuelto"]), D("1.40"))
        self.assertEqual(r.data["pedido"]["estado"], "ENTREGADO")
        self.assertEqual(r.data["venta"]["origen"], "PEDIDO")
        self.refrescar(self.chicle, self.arroz)
        self.assertEqual((self.chicle.stock_actual, self.arroz.stock_actual), (D("96"), D("48")))
        # reintento: no duplica venta ni stock
        r2 = self.client.post(f"/api/pedidos/{pid}/entregar/", pago, format="json")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(Venta.objects.count(), 1)
        self.refrescar(self.chicle)
        self.assertEqual(self.chicle.stock_actual, D("96"))

    def test_entrega_por_transferencia_exige_comprobante(self):
        pid = self.crear_pedido().data["id"]
        self.abrir_turno()
        r = self.client.post(f"/api/pedidos/{pid}/entregar/", {"pagos": [self.tr("3.60", ref="")]}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post(f"/api/pedidos/{pid}/entregar/", {"pagos": [self.tr("3.60", ref="TRX-9")]},
                             format="json")
        self.assertEqual(r.status_code, 201, r.content)

    def test_un_cliente_no_ve_ni_toca_pedidos_ajenos(self):
        pid = self.crear_pedido(self.user_ana).data["id"]
        self.como(self.user_beto)
        self.assertEqual(self.client.get(f"/api/pedidos/{pid}/").status_code, 404)
        self.assertEqual(self.client.post(f"/api/pedidos/{pid}/cancelar/").status_code, 404)
        self.assertEqual(self.client.get("/api/pedidos/").data["count"], 0)
        self.assertEqual(self.client.post(f"/api/pedidos/{pid}/acusar/").status_code, 403)

    def test_cliente_cancela_solo_si_esta_pendiente(self):
        pid = self.crear_pedido().data["id"]
        self.como(self.cajero)
        self.client.post(f"/api/pedidos/{pid}/estado/", {"estado": "EN_PREPARACION"}, format="json")
        self.como(self.user_ana)
        self.assertEqual(self.client.post(f"/api/pedidos/{pid}/cancelar/").status_code, 400)
        pid2 = self.crear_pedido().data["id"]
        r = self.client.post(f"/api/pedidos/{pid2}/cancelar/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["estado"], "CANCELADO")

    def test_transiciones_invalidas_y_limite_de_pedidos_activos(self):
        pid = self.crear_pedido().data["id"]
        self.como(self.cajero)
        r = self.client.post(f"/api/pedidos/{pid}/estado/", {"estado": "LISTO"}, format="json")
        self.assertEqual(r.status_code, 400)  # no se salta pasos
        r = self.client.post(f"/api/pedidos/{pid}/estado/", {"estado": "ENTREGADO"}, format="json")
        self.assertEqual(r.status_code, 400)  # entregar = cobrar
        for _ in range(2):
            self.assertEqual(self.crear_pedido().status_code, 201)
        self.assertEqual(self.crear_pedido().status_code, 400)  # máx. 3 activos

    def test_solo_clientes_crean_pedidos_y_el_personal_no_se_mezcla(self):
        self.assertEqual(self.crear_pedido(self.cajero).status_code, 403)
        self.como(self.user_ana)
        self.assertEqual(self.client.get("/api/ventas/").status_code, 403)
        self.assertEqual(self.client.get("/api/clientes/").status_code, 403)
        self.assertEqual(self.client.get("/api/pedidos/alarma/").status_code, 403)
