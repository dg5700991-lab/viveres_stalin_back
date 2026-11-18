import io
import shutil
import tempfile
from decimal import Decimal as D

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image

from apps.catalogo.models import Producto
from apps.core.models import ErrorSoloAgregar
from apps.inventario.models import MovimientoInventario
from apps.usuarios.models import Usuario

from .base import CLAVE, Base


def png_bytes(size=(1600, 1200)):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


class SeguridadTests(Base):
    # ---------- acceso
    def test_todo_exige_autenticacion(self):
        for url in ("/api/productos/", "/api/ventas/", "/api/clientes/", "/api/pedidos/",
                    "/api/caja/turnos/", "/api/inventario/movimientos/", "/api/mi-cuenta/"):
            self.assertEqual(self.client.get(url).status_code, 401, url)

    def test_permisos_por_rol(self):
        self.como(self.cajero)
        r = self.client.post("/api/productos/", {"tipo": "GRANEL", "nombre": "Pan", "precio_venta": "0.15"},
                             format="json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.client.get("/api/inventario/movimientos/").status_code, 403)
        self.assertEqual(self.client.patch(f"/api/productos/{self.chicle.id}/", {"precio_venta": "0.01"},
                                           format="json").status_code, 403)

    def test_login_registro_y_rol_no_inyectable(self):
        r = self.client.post("/api/auth/login/", {"username": "cajero1", "password": CLAVE}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["rol"], "CAJERO")
        self.assertIn("access", r.data)
        self.assertEqual(self.client.post("/api/auth/login/", {"username": "cajero1", "password": "mala"},
                                          format="json").status_code, 401)
        # registro: password débil rechazada; el rol enviado se ignora SIEMPRE
        base = {"username": "nuevo_cli", "nombre": "Nuevo", "telefono": "0993333333", "rol": "ADMIN",
                "is_superuser": True}
        self.assertEqual(self.client.post("/api/auth/registro/", {**base, "password": "12345678"},
                                          format="json").status_code, 400)
        self.assertEqual(self.client.post("/api/auth/registro/", {**base, "password": "Otra-Clave-Larga-77"},
                                          format="json").status_code, 201)
        u = Usuario.objects.get(username="nuevo_cli")
        self.assertEqual((u.rol, u.is_superuser), ("CLIENTE", False))
        self.assertTrue(u.cliente)

    def test_logout_invalida_el_refresh_token(self):
        tokens = self.client.post("/api/auth/login/", {"username": "cajero1", "password": CLAVE},
                                  format="json").data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        self.assertEqual(self.client.post("/api/auth/logout/", {"refresh": tokens["refresh"]},
                                          format="json").status_code, 204)
        self.client.credentials()
        self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]},
                                          format="json").status_code, 401)

    # ---------- inyección SQL
    def test_sql_injection_en_busqueda_no_hace_nada(self):
        self.como(self.cajero)
        for payload in ("' OR '1'='1", "'; DROP TABLE catalogo_producto; --", "1 UNION SELECT * FROM usuarios_usuario"):
            r = self.client.get("/api/productos/", {"q": payload})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data["count"], 0)  # se trata como texto literal, nunca como SQL
        self.assertEqual(Producto.objects.count(), 2)
        self.assertEqual(self.client.get("/api/productos/por-codigo/1';DROP--/").status_code, 404)
        self.assertEqual(self.client.get("/api/inventario/movimientos/", {"producto": "' OR 1=1"}).status_code, 403)
        self.como(self.admin)
        self.assertEqual(self.client.get("/api/inventario/movimientos/", {"producto": "' OR 1=1"}).status_code, 400)

    # ---------- reglas del catálogo
    def test_reglas_de_producto_con_y_sin_codigo(self):
        self.como(self.admin)
        post = lambda d: self.client.post("/api/productos/", d, format="json")
        self.assertEqual(post({"tipo": "GRANEL", "nombre": "Pan", "codigo_barras": "123456",
                               "precio_venta": "0.15"}).status_code, 400)          # granel no lleva código
        self.assertEqual(post({"tipo": "CODIGO", "nombre": "Cola", "precio_venta": "1"}).status_code, 400)
        self.assertEqual(post({"tipo": "CODIGO", "nombre": "Cola 2", "codigo_barras": "7861000000011",
                               "precio_venta": "1"}).status_code, 400)             # código duplicado
        self.assertEqual(post({"tipo": "CODIGO", "nombre": "Cola 3", "codigo_barras": "12;DROP",
                               "precio_venta": "1"}).status_code, 400)             # formato inválido
        self.assertEqual(post({"tipo": "GRANEL", "nombre": "Arroz", "precio_venta": "1"}).status_code, 400)  # nombre repetido
        self.assertEqual(post({"tipo": "GRANEL", "nombre": "Pan", "unidad_medida": "UND",
                               "precio_venta": "0.15"}).status_code, 201)
        self.assertEqual(post({"tipo": "CODIGO", "nombre": "Cola", "codigo_barras": "7861000000099",
                               "precio_venta": "-1"}).status_code, 400)
        # stock no se puede escribir por el catálogo y los productos no se borran
        r = self.client.patch(f"/api/productos/{self.chicle.id}/", {"stock_actual": "9999"}, format="json")
        self.assertEqual(D(r.data["stock_actual"]), D("100"))
        self.assertEqual(self.client.delete(f"/api/productos/{self.chicle.id}/").status_code, 405)
        self.assertEqual(self.client.patch(f"/api/productos/{self.chicle.id}/", {"tipo": "GRANEL"},
                                           format="json").status_code, 400)

    def test_busqueda_por_codigo_escaneado(self):
        self.como(self.cajero)
        r = self.client.get("/api/productos/por-codigo/7861000000011/")
        self.assertEqual((r.status_code, r.data["nombre"]), (200, "Chicle"))
        self.assertEqual(self.client.get("/api/productos/por-codigo/0000000000/").status_code, 404)
        self.assertEqual(self.client.get("/api/productos/", {"tipo": "GRANEL"}).data["count"], 1)

    def test_visibilidad_de_costo_y_stock_segun_rol(self):
        self.como(self.admin)
        self.assertIn("costo", self.client.get("/api/productos/").data["results"][0])
        self.como(self.cajero)
        fila = self.client.get("/api/productos/").data["results"][0]
        self.assertNotIn("costo", fila)
        self.assertIn("stock_actual", fila)
        self.como(self.user_ana)
        fila = self.client.get("/api/productos/").data["results"][0]
        for campo in ("costo", "stock_actual", "stock_minimo"):
            self.assertNotIn(campo, fila)
        self.assertIn("disponible", fila)

    # ---------- imágenes
    def test_subida_de_imagen_segura(self):
        tmp = tempfile.mkdtemp()
        try:
            with override_settings(MEDIA_ROOT=tmp):
                self.como(self.admin)
                datos = {"tipo": "GRANEL", "nombre": "Lenteja", "precio_venta": "1.00",
                         "imagen": SimpleUploadedFile("../../evil.php.png", png_bytes(), "image/png")}
                r = self.client.post("/api/productos/", datos, format="multipart")
                self.assertEqual(r.status_code, 201, r.content)
                url = r.data["imagen_url"]
                self.assertTrue(url.endswith(".webp"))      # re-codificada, nombre propio (UUID)
                self.assertNotIn("evil", url)
                p = Producto.objects.get(nombre="Lenteja")
                with Image.open(p.imagen.path) as img:
                    self.assertEqual(img.format, "WEBP")
                    self.assertLessEqual(max(img.size), 1024)
                # un archivo que no es imagen (o un script disfrazado) se rechaza
                malo = SimpleUploadedFile("foto.png", b"<?php system($_GET['c']); ?>", "image/png")
                r = self.client.post("/api/productos/", {"tipo": "GRANEL", "nombre": "Fideo",
                                                         "precio_venta": "1.00", "imagen": malo}, format="multipart")
                self.assertEqual(r.status_code, 400)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # ---------- no perder datos
    def test_libros_contables_son_solo_agregar(self):
        self.abrir_turno()
        self.vender(self.items((self.chicle, 1)), [self.ef("0.50")])
        mov = MovimientoInventario.objects.get()
        mov.cantidad = D("-99")
        with self.assertRaises(ErrorSoloAgregar):
            mov.save()
        with self.assertRaises(ErrorSoloAgregar):
            mov.delete()
        with self.assertRaises(ErrorSoloAgregar):
            MovimientoInventario.objects.update(cantidad=0)

    def test_no_se_puede_borrar_un_producto_con_historial(self):
        from django.db.models import ProtectedError
        self.abrir_turno()
        self.vender(self.items((self.chicle, 1)), [self.ef("0.50")])
        with self.assertRaises(ProtectedError):
            self.chicle.delete()

    def test_auditoria_registra_acciones_criticas(self):
        from apps.core.models import AuditLog
        self.abrir_turno()
        self.vender(self.items((self.chicle, 1)), [self.ef("0.50")])
        self.como(self.admin)
        self.client.patch(f"/api/productos/{self.chicle.id}/", {"precio_venta": "0.60"}, format="json")
        acciones = set(AuditLog.objects.values_list("accion", flat=True))
        self.assertTrue({"TURNO_ABIERTO", "VENTA_CREADA", "PRECIO_CAMBIADO"} <= acciones)
