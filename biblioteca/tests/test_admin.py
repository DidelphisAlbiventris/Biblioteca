from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from biblioteca.management.commands.datos_demo import cargar_datos
from biblioteca.models import Autor, Categoria, Ejemplar, Estudiante, Libro, Prestamo


class AdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cargar_datos()
        # Contraseña inutilizable: la autenticación de pruebas usa force_login.
        cls.usuario = get_user_model().objects.create_superuser(username="pruebas", email="pruebas@example.com", password=None)

    def setUp(self):
        self.client.force_login(self.usuario)

    def test_listados_y_formularios_de_los_seis_modelos(self):
        for modelo in (Categoria, Autor, Libro, Ejemplar, Estudiante, Prestamo):
            nombre = modelo._meta.model_name
            for vista in ("changelist", "add"):
                with self.subTest(modelo=nombre, vista=vista):
                    self.assertEqual(self.client.get(reverse(f"admin:biblioteca_{nombre}_{vista}")).status_code, 200)
            objeto = modelo.objects.first()
            with self.subTest(modelo=nombre, vista="change"):
                self.assertEqual(self.client.get(reverse(f"admin:biblioteca_{nombre}_change", args=[objeto.pk])).status_code, 200)

    def test_inicio_redirige_a_admin_y_login_protege_datos(self):
        self.assertRedirects(self.client.get("/"), reverse("admin:index"))
        self.client.logout()
        self.assertEqual(self.client.get(reverse("admin:biblioteca_prestamo_changelist")).status_code, 302)

    def test_busqueda_estudiante_por_codigo_y_nombre(self):
        for texto in ("1150001", "Ana Torres"):
            respuesta = self.client.get(reverse("admin:biblioteca_estudiante_changelist"), {"q": texto})
            self.assertEqual(respuesta.context["cl"].result_count, 1)
            self.assertContains(respuesta, "Ana Torres")

    def test_autocompletar_muestra_codigo_y_titulo_copia(self):
        respuesta = self.client.get(reverse("admin:autocomplete"), {
            "app_label": "biblioteca", "model_name": "prestamo", "field_name": "ejemplar", "term": "INV-001",
        })
        self.assertEqual(respuesta.status_code, 200)
        resultados = respuesta.json()["results"]
        self.assertEqual(len(resultados), 1)
        self.assertIn("INV-001", resultados[0]["text"])
        self.assertIn("Cien años de soledad", resultados[0]["text"])

    def test_filtros_activos_devueltos_y_vencidos(self):
        for estado, numero in (("activo", 3), ("devuelto", 3), ("vencido", 3)):
            respuesta = self.client.get(reverse("admin:biblioteca_prestamo_changelist"), {"estado": estado})
            self.assertEqual(respuesta.context["cl"].result_count, numero)

    def test_formulario_rechaza_segundo_prestamo_y_no_guarda(self):
        respuesta = self.client.post(reverse("admin:biblioteca_prestamo_add"), {
            "estudiante": Estudiante.objects.get(codigo="1150004").pk,
            "ejemplar": Ejemplar.objects.get(codigo_inventario="INV-001").pk,
            "fecha_salida": "2026-11-22", "fecha_limite": "2026-11-29", "fecha_devolucion": "", "_save": "Guardar",
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Esta copia ya tiene un préstamo activo")
        self.assertEqual(Prestamo.objects.count(), 6)

    def test_registrar_prestamo_y_devolver_en_formulario(self):
        copia = Ejemplar.objects.get(codigo_inventario="INV-003")
        datos = {"estudiante": Estudiante.objects.get(codigo="1150004").pk, "ejemplar": copia.pk,
                 "fecha_salida": "2026-11-22", "fecha_limite": "2026-11-29", "fecha_devolucion": "", "_save": "Guardar"}
        respuesta = self.client.post(reverse("admin:biblioteca_prestamo_add"), datos)
        self.assertEqual(respuesta.status_code, 302)
        prestamo = Prestamo.objects.get(ejemplar=copia)
        datos["fecha_devolucion"] = "2026-11-22"
        respuesta = self.client.post(reverse("admin:biblioteca_prestamo_change", args=[prestamo.pk]), datos)
        self.assertEqual(respuesta.status_code, 302)
        prestamo.refresh_from_db()
        self.assertFalse(prestamo.activo)

    def test_accion_devuelve_activos_sin_alterar_historicos(self):
        historico = Prestamo.objects.filter(fecha_devolucion__isnull=False).first()
        fecha_anterior = historico.fecha_devolucion
        respuesta = self.client.post(reverse("admin:biblioteca_prestamo_changelist"), {
            "action": "marcar_devueltos", "_selected_action": list(Prestamo.objects.values_list("pk", flat=True)),
        })
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Prestamo.objects.filter(fecha_devolucion__isnull=True).count(), 0)
        historico.refresh_from_db()
        self.assertEqual(historico.fecha_devolucion, fecha_anterior)

    def test_accion_no_devuelve_antes_de_fecha_salida(self):
        manana = timezone.localdate() + timedelta(days=1)
        prestamo = Prestamo.objects.create(ejemplar=Ejemplar.objects.get(codigo_inventario="INV-003"),
                                          estudiante=Estudiante.objects.first(), fecha_salida=manana, fecha_limite=manana)
        self.client.post(reverse("admin:biblioteca_prestamo_changelist"), {
            "action": "marcar_devueltos", "_selected_action": [prestamo.pk],
        })
        prestamo.refresh_from_db()
        self.assertIsNone(prestamo.fecha_devolucion)

    def test_inline_y_solo_lectura_configurados(self):
        self.assertTrue(admin.site._registry[Libro].inlines)
        self.assertIn("creado_en", admin.site._registry[Estudiante].readonly_fields)
        for modelo in (Libro, Ejemplar, Estudiante, Prestamo):
            panel = admin.site._registry[modelo]
            self.assertTrue(panel.list_display)
            self.assertTrue(panel.search_fields)
            self.assertTrue(panel.list_filter)
