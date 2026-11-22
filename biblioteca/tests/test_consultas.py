from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from biblioteca.consultas import ejecutar_retos, ejemplos_adicionales, medir_consultas
from biblioteca.management.commands.datos_demo import cargar_datos
from biblioteca.models import Autor, Categoria, Ejemplar, Estudiante, Libro, Prestamo


class ConsultasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cargar_datos()

    def test_cantidad_minima_datos_y_estados(self):
        for modelo, esperado in [(Categoria, 2), (Autor, 3), (Libro, 5), (Ejemplar, 8), (Estudiante, 4), (Prestamo, 6)]:
            self.assertEqual(modelo.objects.count(), esperado)
        self.assertEqual(Prestamo.objects.filter(fecha_devolucion__isnull=True).count(), 3)

    def test_carga_idempotente(self):
        call_command("datos_demo", stdout=StringIO())
        call_command("datos_demo", stdout=StringIO())
        self.test_cantidad_minima_datos_y_estados()

    def test_carga_no_sobrescribe_cambios_usuario(self):
        estudiante = Estudiante.objects.get(codigo="1150001")
        estudiante.nombre = "Nombre corregido"
        estudiante.save()
        prestamo = Prestamo.objects.get(ejemplar__codigo_inventario="INV-001", fecha_devolucion__isnull=True)
        prestamo.fecha_devolucion = timezone.localdate()
        prestamo.save()
        cargar_datos()
        estudiante.refresh_from_db()
        prestamo.refresh_from_db()
        self.assertEqual(estudiante.nombre, "Nombre corregido")
        self.assertEqual(prestamo.fecha_devolucion, timezone.localdate())
        self.assertEqual(Prestamo.objects.count(), 6)

    def test_retos_devuelven_resultados_documentados(self):
        retos = {r["reto"]: r["resultado"] for r in ejecutar_retos()}
        self.assertEqual(len(retos), 10)
        self.assertEqual(retos[1]["copias"], ["PRACTICA-01", "PRACTICA-02"])
        self.assertEqual(retos[2], ["Cien años de soledad", "El amor en los tiempos del cólera"])
        self.assertEqual(retos[3], ["Código limpio"])
        self.assertEqual(retos[4], ["INV-002", "INV-003", "INV-005", "INV-006", "INV-008", "PRACTICA-01", "PRACTICA-02"])
        self.assertEqual(retos[5], ["Ana Torres", "Luis Pérez", "María Rojas"])
        self.assertEqual([r["total_prestamos"] for r in retos[6]], [3, 2, 1, 0])
        self.assertEqual(retos[7], {"titulo": "Cien años de soledad", "total_prestamos": 3})
        self.assertEqual(retos[8], ["Pedro Gómez"])
        self.assertEqual(retos[9]["fecha_devolucion"], timezone.localdate().isoformat())
        self.assertFalse(retos[9]["activo"])
        self.assertTrue(retos[9]["disponible"])
        self.assertEqual(retos[10], {"autor_existe": False, "libro_existe": True, "autores_del_libro": [], "copias_del_libro": 2})

    def test_retos_se_revierten_y_pueden_repetirse(self):
        ejecutar_retos()
        ejecutar_retos()
        self.test_cantidad_minima_datos_y_estados()
        self.assertFalse(Autor.objects.filter(nombre="Autor de práctica").exists())

    def test_disponibles_excluye_copia_con_historial_devuelto_y_activo(self):
        # INV-001 tiene ambos estados: no basta filtrar por algún préstamo devuelto.
        activos = Prestamo.objects.filter(fecha_devolucion__isnull=True).values("ejemplar_id")
        disponibles = list(Ejemplar.objects.exclude(pk__in=activos).values_list("codigo_inventario", flat=True))
        self.assertEqual(disponibles, ["INV-002", "INV-003", "INV-005", "INV-006", "INV-008"])

    def test_medicion_real_n_mas_uno(self):
        medidas = medir_consultas()
        self.assertEqual(medidas["prestamos"], {"registros": 6, "prediccion_antes": 19, "antes": 19, "despues": 1, "mismos_resultados": True})
        self.assertEqual(medidas["libros_autores"], {"registros": 5, "prediccion_antes": 6, "antes": 6, "despues": 2, "mismos_resultados": True})

    def test_mediciones_se_mantienen_con_mas_datos(self):
        copia = Ejemplar.objects.get(codigo_inventario="INV-003")
        estudiante = Estudiante.objects.get(codigo="1150004")
        Prestamo.objects.create(ejemplar=copia, estudiante=estudiante, fecha_limite=timezone.localdate())
        medidas = medir_consultas()
        self.assertEqual(medidas["prestamos"]["antes"], 22)
        self.assertEqual(medidas["prestamos"]["despues"], 1)

    def test_medicion_con_catalogo_vacio(self):
        Prestamo.objects.all().delete()
        Ejemplar.objects.all().delete()
        Libro.objects.all().delete()
        medidas = medir_consultas()
        self.assertEqual(medidas["prestamos"]["antes"], 1)
        self.assertEqual(medidas["prestamos"]["despues"], 1)
        self.assertEqual(medidas["libros_autores"]["despues"], 1)

    def test_comando_demostracion_es_json_y_no_cambia_datos(self):
        import json
        salida = StringIO()
        call_command("demostrar_orm", stdout=salida)
        informe = json.loads(salida.getvalue())
        self.assertEqual(len(informe["retos"]), 10)
        self.test_cantidad_minima_datos_y_estados()

    def test_ejemplos_adicionales_q_y_aggregate(self):
        ejemplos = ejemplos_adicionales()
        self.assertEqual(len(ejemplos["novela_o_ingenieria"]), 5)
        self.assertEqual(ejemplos["prestamos_totales"], {"total": 6})
