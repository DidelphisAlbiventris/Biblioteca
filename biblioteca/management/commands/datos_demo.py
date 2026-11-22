"""Datos ficticios, deterministas y sin borrados: se pueden cargar varias veces."""
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from biblioteca.models import Autor, Categoria, Ejemplar, Estudiante, Libro, Prestamo


def cargar_datos():
    novela, _ = Categoria.objects.get_or_create(nombre="Novela", defaults={"descripcion": "Literatura narrativa"})
    ingenieria, _ = Categoria.objects.get_or_create(nombre="Ingeniería", defaults={"descripcion": "Ingeniería de software"})
    autores = {}
    for nombre in ("Gabriel García Márquez", "Isabel Allende", "Robert C. Martin"):
        autores[nombre], _ = Autor.objects.get_or_create(nombre=nombre)

    catalogo = [
        ("9780307474728", "Cien años de soledad", 1967, novela, "Gabriel García Márquez", ["INV-001", "INV-002"]),
        ("9780307389732", "El amor en los tiempos del cólera", 1985, novela, "Gabriel García Márquez", ["INV-003"]),
        ("9788401352895", "La casa de los espíritus", 1982, novela, "Isabel Allende", ["INV-004", "INV-005"]),
        ("9780132350884", "Código limpio", 2008, ingenieria, "Robert C. Martin", ["INV-006", "INV-007"]),
        ("9780134494166", "Arquitectura limpia", 2017, ingenieria, "Robert C. Martin", ["INV-008"]),
    ]
    copias = {}
    for isbn, titulo, anio, categoria, autor, codigos in catalogo:
        libro, creado = Libro.objects.get_or_create(isbn=isbn, defaults={
            "titulo": titulo, "anio_publicacion": anio, "categoria": categoria, "idioma": "Español",
        })
        if creado:
            libro.autores.add(autores[autor])
        for codigo in codigos:
            copias[codigo], _ = Ejemplar.objects.get_or_create(codigo_inventario=codigo, defaults={
                "libro": libro, "condicion": Ejemplar.Condicion.USADO,
                "nota": "Copia de demostración en buen estado.",
            })
            if copias[codigo].libro_id != libro.pk:
                raise CommandError(f"El código {codigo} ya pertenece a otro libro; no se modificó el inventario.")

    estudiantes = {}
    for codigo, nombre, correo in [
        ("1150001", "Ana Torres", "ana.torres@example.com"),
        ("1150002", "Luis Pérez", "luis.perez@example.com"),
        ("1150003", "María Rojas", "maria.rojas@example.com"),
        ("1150004", "Pedro Gómez", "pedro.gomez@example.com"),
    ]:
        estudiantes[codigo], _ = Estudiante.objects.get_or_create(codigo=codigo, defaults={"nombre": nombre, "correo": correo})

    # Enero de 2026: fechas fijas para que repetir el comando no cree otros préstamos.
    movimientos = [
        ("INV-001", "1150001", 1, 8, 6),
        ("INV-002", "1150001", 2, 9, 8),
        ("INV-006", "1150002", 3, 10, 9),
        ("INV-001", "1150002", 10, 17, None),
        ("INV-004", "1150001", 11, 18, None),
        ("INV-007", "1150003", 12, 19, None),
    ]
    for codigo, estudiante, salida, limite, devolucion in movimientos:
        Prestamo.objects.get_or_create(
            ejemplar=copias[codigo], estudiante=estudiantes[estudiante], fecha_salida=date(2026, 1, salida),
            defaults={"fecha_limite": date(2026, 1, limite),
                      "fecha_devolucion": date(2026, 1, devolucion) if devolucion else None},
        )


class Command(BaseCommand):
    help = "Carga 5 libros, 3 autores, 8 copias, 4 estudiantes y 6 préstamos ficticios; no borra ni sobrescribe datos."

    def handle(self, *args, **options):
        try:
            with transaction.atomic():
                cargar_datos()
        except IntegrityError as exc:
            raise CommandError("Los datos existentes entran en conflicto con la demostración. No se guardó ningún cambio.") from exc
        totales = ", ".join(f"{modelo._meta.verbose_name_plural}: {modelo.objects.count()}" for modelo in
                            (Categoria, Autor, Libro, Ejemplar, Estudiante, Prestamo))
        self.stdout.write(self.style.SUCCESS(f"Datos listos. {totales}."))
