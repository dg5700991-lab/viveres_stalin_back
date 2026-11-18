from decimal import Decimal as D

from apps.clientes.models import MovimientoFiado
from apps.core.models import ErrorSoloAgregar

from .base import Base


class FiadosTests(Base):
    def test_flujo_de_fiado_libreta_y_abonos(self):
        self.abrir_turno()
        v1 = self.vender(self.items((self.chicle, 10)), [self.fi("5.00")], cliente=self.ana)
        self.assertEqual(v1.status_code, 201, v1.content)
        self.vender(self.items((self.arroz, 5)), [self.fi("4.00")], cliente=self.ana)
        self.refrescar(self.ana)
        self.assertEqual(self.ana.saldo_fiado, D("9.00"))

        # Abono mayor a la deuda → rechazado; abono válido → baja el saldo
        r = self.client.post(f"/api/clientes/{self.ana.id}/abono/", {"monto": "10", "metodo": "EFECTIVO"},
                             format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post(f"/api/clientes/{self.ana.id}/abono/", {"monto": "6.00", "metodo": "EFECTIVO"},
                             format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(D(r.data["saldo_resultante"]), D("3.00"))

        libreta = self.client.get(f"/api/clientes/{self.ana.id}/libreta/").data
        self.assertEqual(D(libreta["saldo"]), D("3.00"))
        self.assertEqual([m["tipo"] for m in libreta["movimientos"]], ["ABONO", "CARGO", "CARGO"])

        # ¿Quién debe y cuánto?
        d = self.client.get("/api/clientes/deudores/").data
        self.assertEqual(D(d["total_por_cobrar"]), D("3.00"))
        self.assertEqual([c["nombre"] for c in d["clientes"]], ["Ana"])

    def test_pago_mixto_efectivo_y_fiado(self):
        self.abrir_turno()
        r = self.vender(self.items((self.chicle, 10)), [self.ef("2.00"), self.fi("3.00")], cliente=self.ana)
        self.assertEqual(r.status_code, 201)
        self.refrescar(self.ana)
        self.assertEqual(self.ana.saldo_fiado, D("3.00"))

    def test_limite_de_credito_solo_lo_define_el_admin(self):
        self.como(self.cajero)
        r = self.client.patch(f"/api/clientes/{self.ana.id}/", {"limite_credito": "100"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.como(self.admin)
        r = self.client.patch(f"/api/clientes/{self.ana.id}/", {"limite_credito": "8.00"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.abrir_turno()
        r = self.vender(self.items((self.chicle, 20)), [self.fi("10.00")], cliente=self.ana)
        self.assertEqual(r.status_code, 400)  # supera el límite
        self.refrescar(self.ana, self.chicle)
        self.assertEqual((self.ana.saldo_fiado, self.chicle.stock_actual), (D("0"), D("100")))  # nada quedó a medias

    def test_anular_venta_fiada_revierte_la_deuda(self):
        self.abrir_turno()
        v = self.vender(self.items((self.chicle, 10)), [self.fi("5.00")], cliente=self.ana).data
        self.como(self.admin)
        self.assertEqual(self.client.post(f"/api/ventas/{v['id']}/anular/", {"motivo": "Error"},
                                          format="json").status_code, 200)
        self.refrescar(self.ana)
        self.assertEqual(self.ana.saldo_fiado, D("0.00"))
        self.assertEqual(MovimientoFiado.objects.filter(cliente=self.ana).count(), 2)  # cargo + reverso

    def test_no_se_anula_si_el_cliente_ya_abono_a_esa_deuda(self):
        self.abrir_turno()
        v = self.vender(self.items((self.chicle, 10)), [self.fi("5.00")], cliente=self.ana).data
        self.client.post(f"/api/clientes/{self.ana.id}/abono/", {"monto": "3.00", "metodo": "EFECTIVO"},
                         format="json")
        self.como(self.admin)
        r = self.client.post(f"/api/ventas/{v['id']}/anular/", {"motivo": "Error"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.refrescar(self.ana, self.chicle)
        self.assertEqual((self.ana.saldo_fiado, self.chicle.stock_actual), (D("2.00"), D("90")))

    def test_la_libreta_es_inmutable(self):
        self.abrir_turno()
        self.vender(self.items((self.chicle, 10)), [self.fi("5.00")], cliente=self.ana)
        mov = MovimientoFiado.objects.get()
        mov.monto = D("1.00")
        with self.assertRaises(ErrorSoloAgregar):
            mov.save()
        with self.assertRaises(ErrorSoloAgregar):
            mov.delete()
        with self.assertRaises(ErrorSoloAgregar):
            MovimientoFiado.objects.all().update(monto=D("0.01"))
        with self.assertRaises(ErrorSoloAgregar):
            MovimientoFiado.objects.all().delete()

    def test_el_cliente_ve_solo_su_propia_libreta(self):
        self.abrir_turno()
        self.vender(self.items((self.chicle, 10)), [self.fi("5.00")], cliente=self.ana)
        self.como(self.user_ana)
        self.assertEqual(D(self.client.get("/api/mi-cuenta/").data["saldo"]), D("5.00"))
        self.como(self.user_beto)
        self.assertEqual(D(self.client.get("/api/mi-cuenta/").data["saldo"]), D("0.00"))
        self.assertEqual(self.client.get(f"/api/clientes/{self.ana.id}/libreta/").status_code, 403)
