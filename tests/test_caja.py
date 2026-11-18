from decimal import Decimal as D

from apps.caja.models import Turno
from apps.core.models import ErrorSoloAgregar

from .base import Base


class CajaTests(Base):
    def test_no_se_vende_sin_turno_y_solo_un_turno_abierto(self):
        self.como(self.cajero)
        r = self.vender(self.items((self.chicle, 1)), [self.ef("0.50")])
        self.assertEqual(r.status_code, 400)
        self.abrir_turno()
        r = self.client.post("/api/caja/turnos/abrir/", {"fondo_inicial": "10"}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_cuadre_completo_por_metodo_de_pago(self):
        self.abrir_turno(fondo="50.00")
        # ventas: efectivo 1.00 | transferencia 4.00 | fiado 5.00
        self.assertEqual(self.vender(self.items((self.chicle, 2)), [self.ef("1.00")]).status_code, 201)
        self.assertEqual(self.vender(self.items((self.arroz, 5)), [self.tr("4.00")]).status_code, 201)
        self.assertEqual(self.vender(self.items((self.chicle, 10)), [self.fi("5.00")],
                                     cliente=self.ana).status_code, 201)
        # abonos de Ana: efectivo 3.00, transferencia 2.00 | retiro de caja 4.00
        r = self.client.post(f"/api/clientes/{self.ana.id}/abono/", {"monto": "3.00", "metodo": "EFECTIVO"},
                             format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = self.client.post(f"/api/clientes/{self.ana.id}/abono/", {
            "monto": "2.00", "metodo": "TRANSFERENCIA", "referencia": "TRX-777"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        r = self.client.post("/api/caja/turnos/movimientos/", {"tipo": "EGRESO", "monto": "4.00",
                                                              "motivo": "Pago al proveedor de pan"}, format="json")
        self.assertEqual(r.status_code, 201, r.content)

        # El cajero NO ve el esperado antes de contar (conteo a ciegas)
        self.assertNotIn("cuadre_parcial", self.client.get("/api/caja/turnos/actual/").data)
        self.como(self.admin)
        # esperado efectivo = 50 (fondo) + 1 (ventas) + 3 (abono) - 4 (retiro) = 50 | transferencia = 4 + 2 = 6
        parcial = self.client.get("/api/caja/turnos/actual/")
        self.assertEqual(parcial.status_code, 404)  # el admin no tiene turno propio abierto

        self.como(self.cajero)
        r = self.client.post("/api/caja/turnos/cerrar/", {"contado_efectivo": "49.00",
                                                         "contado_transferencia": "6.00"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        c = r.data["cuadre"]
        self.assertEqual(D(c["esperado_efectivo"]), D("50.00"))
        self.assertEqual(D(c["esperado_transferencia"]), D("6.00"))
        self.assertEqual(D(c["ventas_fiado"]), D("5.00"))
        self.assertEqual(c["num_ventas"], 3)
        t = r.data["turno"]
        self.assertEqual(D(t["diferencia_efectivo"]), D("-1.00"))       # faltó 1.00
        self.assertEqual(D(t["diferencia_transferencia"]), D("0.00"))   # cuadra
        self.assertEqual(t["estado"], "CERRADO")

    def test_turno_cerrado_es_inmutable_y_ya_no_cobra(self):
        self.abrir_turno()
        self.client.post("/api/caja/turnos/cerrar/", {"contado_efectivo": "50", "contado_transferencia": "0"},
                         format="json")
        turno = Turno.objects.get()
        turno.contado_efectivo = D("999")
        with self.assertRaises(ErrorSoloAgregar):
            turno.save()
        with self.assertRaises(ErrorSoloAgregar):
            turno.delete()
        self.assertEqual(self.vender(self.items((self.chicle, 1)), [self.ef("0.50")]).status_code, 400)

    def test_anulacion_cambia_el_cuadre_y_no_se_anula_con_turno_cerrado(self):
        self.abrir_turno(fondo="10.00")
        v = self.vender(self.items((self.chicle, 10)), [self.ef("5.00")]).data
        self.como(self.admin)
        self.client.post(f"/api/ventas/{v['id']}/anular/", {"motivo": "Error"}, format="json")
        turno = Turno.objects.get()
        r = self.client.get(f"/api/caja/turnos/{turno.id}/cuadre/")
        self.assertEqual(D(r.data["cuadre"]["esperado_efectivo"]), D("10.00"))
        self.como(self.cajero)
        self.client.post("/api/caja/turnos/cerrar/", {"contado_efectivo": "10", "contado_transferencia": "0"},
                         format="json")
        v2 = Turno.objects.get()
        self.assertEqual(v2.diferencia_efectivo, D("0.00"))

    def test_validaciones_de_pago(self):
        self.abrir_turno()
        it = self.items((self.chicle, 2))  # total 1.00
        self.assertEqual(self.vender(it, [self.ef("0.90")]).status_code, 400)          # no suma el total
        self.assertEqual(self.vender(it, [self.tr("1.00", ref="")]).status_code, 400)  # sin comprobante
        self.assertEqual(self.vender(it, [self.fi("1.00")]).status_code, 400)          # fiado sin cliente
        r = self.vender(it, [self.tr("0.40"), self.ef("0.60")], efectivo_recibido="1.00")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(D(r.data["vuelto"]), D("0.40"))
