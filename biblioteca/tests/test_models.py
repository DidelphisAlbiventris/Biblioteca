from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.forms import modelform_factory
from django.test import TestCase
from django.utils import timezone

from biblioteca.models import Autor, Categoria, Ejemplar, Estudiante, Libro, Prestamo


class ModelosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.categoria = Categoria.objects.create(nombre="Ingeniería")
        cls.autor = Autor.objects.create(nombre="Autora de pruebas")
        cls.libro = Libro.objects.create(titulo="Libro de pruebas", anio_publicacion=2020,
                                        isbn="9780132350884", categoria=cls.categoria)
        cls.libro.autores.add(cls.autor)
        cls.copia = Ejemplar.objects.create(libro=cls.libro, codigo_inventario="PRUEBA-01")
        cls.estudiante = Estudiante.objects.create(codigo="1151", nombre="Ana", correo="ana@example.com")
        cls.otro = Estudiante.objects.create(codigo="1152", nombre="Luis", correo="luis@example.com")

    def prestar(self, **cambios):
        datos = {"ejemplar": self.copia, "estudiante": self.estudiante,
                 "fecha_salida": timezone.localdate(), "fecha_limite": timezone.localdate() + timedelta(days=7)}
        datos.update(cambios)
        return Prestamo.objects.create(**datos)

    def test_base_de_datos_impide_dos_activos_sin_full_clean(self):
        self.prestar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.prestar(estudiante=self.otro)
        self.assertEqual(Prestamo.objects.count(), 1)

    def test_clean_da_mensaje_en_campo_ejemplar(self):
        self.prestar()
        duplicado = Prestamo(ejemplar=self.copia, estudiante=self.otro,
                             fecha_salida=timezone.localdate(), fecha_limite=timezone.localdate())
        with self.assertRaises(ValidationError) as error:
            duplicado.full_clean()
        self.assertIn("ejemplar", error.exception.message_dict)

    def test_editar_prestamo_activo_no_lo_confunde_con_otro(self):
        prestamo = self.prestar()
        prestamo.full_clean()

    def test_devolver_libera_copia_y_conserva_historial(self):
        primero = self.prestar()
        primero.fecha_devolucion = timezone.localdate()
        primero.save(update_fields=["fecha_devolucion"])
        segundo = self.prestar(estudiante=self.otro)
        self.assertTrue(segundo.activo)
        self.assertEqual(Prestamo.objects.filter(ejemplar=self.copia).count(), 2)

    def test_permite_varios_prestamos_historicos_de_misma_copia(self):
        self.prestar(fecha_devolucion=timezone.localdate())
        self.prestar(fecha_devolucion=timezone.localdate())
        self.prestar()
        self.assertEqual(Prestamo.objects.count(), 3)

    def test_reabrir_historico_con_activo_falla_en_base(self):
        historico = self.prestar(fecha_devolucion=timezone.localdate())
        self.prestar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Prestamo.objects.filter(pk=historico.pk).update(fecha_devolucion=None)

    def test_limite_anterior_salida_falla_incluso_con_create(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.prestar(fecha_limite=timezone.localdate() - timedelta(days=1))

    def test_devolucion_anterior_salida_falla_incluso_con_create(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.prestar(fecha_devolucion=timezone.localdate() - timedelta(days=1))

    def test_fechas_iguales_son_validas(self):
        prestamo = self.prestar(fecha_limite=timezone.localdate(), fecha_devolucion=timezone.localdate())
        prestamo.full_clean()

    def test_fecha_devolucion_admite_null_y_formulario_vacio(self):
        campo = Prestamo._meta.get_field("fecha_devolucion")
        self.assertTrue(campo.null)
        self.assertTrue(campo.blank)
        formulario = modelform_factory(Prestamo, fields="__all__")({
            "ejemplar": self.copia.pk, "estudiante": self.estudiante.pk,
            "fecha_salida": "2026-01-01", "fecha_limite": "2026-01-08", "fecha_devolucion": "",
        })
        self.assertTrue(formulario.is_valid(), formulario.errors)
        self.assertIsNone(formulario.save().fecha_devolucion)

    def test_no_borrar_estudiante_con_historial(self):
        self.prestar(fecha_devolucion=timezone.localdate())
        with self.assertRaises(ProtectedError):
            self.estudiante.delete()

    def test_no_borrar_ejemplar_con_historial(self):
        self.prestar()
        with self.assertRaises(ProtectedError):
            self.copia.delete()

    def test_no_borrar_libro_con_copias(self):
        with self.assertRaises(ProtectedError):
            self.libro.delete()

    def test_no_borrar_categoria_con_libros(self):
        with self.assertRaises(ProtectedError):
            self.categoria.delete()

    def test_borrar_autor_solo_borra_enlace_no_libro(self):
        self.autor.delete()
        self.assertTrue(Libro.objects.filter(pk=self.libro.pk).exists())
        self.assertEqual(self.libro.autores.count(), 0)
        self.assertTrue(Ejemplar.objects.filter(pk=self.copia.pk).exists())

    def test_muchos_a_muchos_permite_coautoria(self):
        segundo = Autor.objects.create(nombre="Coautor")
        self.libro.autores.add(segundo)
        self.assertEqual(self.libro.autores.count(), 2)
        self.assertEqual(segundo.libros.get(), self.libro)

    def test_codigos_isbn_correo_no_se_repiten(self):
        for modelo, datos in [
            (Libro, {"titulo": "Otro", "anio_publicacion": 2021, "isbn": self.libro.isbn, "categoria": self.categoria}),
            (Ejemplar, {"libro": self.libro, "codigo_inventario": self.copia.codigo_inventario}),
            (Estudiante, {"codigo": self.estudiante.codigo, "nombre": "Otra", "correo": "otra@example.com"}),
            (Estudiante, {"codigo": "1153", "nombre": "Otra", "correo": self.estudiante.correo}),
        ]:
            with self.subTest(modelo=modelo.__name__, datos=datos):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    modelo.objects.create(**datos)

    def test_anio_cero_no_se_puede_guardar(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Libro.objects.filter(pk=self.libro.pk).update(anio_publicacion=0)

    def test_condicion_invalida_no_se_puede_guardar(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ejemplar.objects.filter(pk=self.copia.pk).update(condicion="inexistente")

    def test_validadores_correo_isbn(self):
        self.estudiante.correo = "sin-correo"
        with self.assertRaises(ValidationError):
            self.estudiante.full_clean()
        self.libro.isbn = "ISBN incorrecto"
        with self.assertRaises(ValidationError):
            self.libro.full_clean()

    def test_str_legible_en_los_seis_modelos(self):
        prestamo = self.prestar()
        for objeto, esperado in [(self.categoria, "Ingeniería"), (self.autor, "Autora de pruebas"),
                                 (self.libro, "Libro de pruebas"), (self.copia, "PRUEBA-01"),
                                 (self.estudiante, "Ana"), (prestamo, "activo")]:
            with self.subTest(modelo=type(objeto).__name__):
                self.assertIn(esperado, str(objeto))
