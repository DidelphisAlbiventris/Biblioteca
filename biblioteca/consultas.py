"""Consultas reproducibles de las fases 5 y 6 del PDF.

Los retos que escriben se ejecutan en una transacción que se revierte al final:
los resultados se calculan de verdad y el catálogo original queda disponible.
"""
from django.db import connection, transaction
from django.db.models import Count, Q
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from .models import Autor, Categoria, Ejemplar, Estudiante, Libro, Prestamo


def medir_consultas():
    cantidad_prestamos = Prestamo.objects.count()
    cantidad_libros = Libro.objects.count()

    with CaptureQueriesContext(connection) as antes_prestamos:
        filas_antes = [(p.estudiante.nombre, p.ejemplar.libro.titulo) for p in Prestamo.objects.all()]
    with CaptureQueriesContext(connection) as despues_prestamos:
        filas_despues = [(p.estudiante.nombre, p.ejemplar.libro.titulo)
                        for p in Prestamo.objects.select_related("estudiante", "ejemplar__libro")]

    with CaptureQueriesContext(connection) as antes_autores:
        autores_antes = [(libro.titulo, [autor.nombre for autor in libro.autores.all()])
                         for libro in Libro.objects.all()]
    with CaptureQueriesContext(connection) as despues_autores:
        autores_despues = [(libro.titulo, [autor.nombre for autor in libro.autores.all()])
                           for libro in Libro.objects.prefetch_related("autores")]

    return {
        "prestamos": {"registros": cantidad_prestamos, "prediccion_antes": 1 + 3 * cantidad_prestamos,
                      "antes": len(antes_prestamos), "despues": len(despues_prestamos),
                      "mismos_resultados": filas_antes == filas_despues},
        "libros_autores": {"registros": cantidad_libros, "prediccion_antes": 1 + cantidad_libros,
                          "antes": len(antes_autores), "despues": len(despues_autores),
                          "mismos_resultados": autores_antes == autores_despues},
    }


@transaction.atomic
def ejecutar_retos():
    resultados = []

    # 1. Predicción: se crean un autor, un libro asociado y dos copias distintas.
    autor = Autor.objects.create(nombre="Autor de práctica")
    categoria = Categoria.objects.get(nombre="Novela")
    libro = Libro.objects.create(titulo="Libro creado desde el shell", anio_publicacion=2026,
                                 isbn="9780306406157", categoria=categoria)
    libro.autores.add(autor)
    Ejemplar.objects.create(libro=libro, codigo_inventario="PRACTICA-01")
    Ejemplar.objects.create(libro=libro, codigo_inventario="PRACTICA-02")
    resultados.append({"reto": 1, "resultado": {"autor": autor.nombre, "libro": libro.titulo,
                       "copias": list(libro.ejemplares.values_list("codigo_inventario", flat=True))}})

    # 2. Predicción: los dos libros de Gabriel García Márquez del catálogo demo.
    resultados.append({"reto": 2, "resultado": list(Libro.objects.filter(
        autores__nombre="Gabriel García Márquez").values_list("titulo", flat=True))})

    # 3. Predicción: buscar LIMPIO devuelve Código limpio sin exigir mayúsculas.
    resultados.append({"reto": 3, "resultado": list(Libro.objects.filter(
        titulo__icontains="LIMPIO").values_list("titulo", flat=True))})

    # 4. Predicción: cinco copias originales y las dos nuevas; no INV-001, 004, 007.
    activos = Prestamo.objects.filter(fecha_devolucion__isnull=True).values("ejemplar_id")
    disponibles = Ejemplar.objects.exclude(pk__in=activos)
    resultados.append({"reto": 4, "resultado": list(disponibles.values_list("codigo_inventario", flat=True))})

    # 5. Predicción: Ana, Luis y María, una vez cada estudiante.
    resultados.append({"reto": 5, "resultado": list(Estudiante.objects.filter(
        prestamos__fecha_devolucion__isnull=True, prestamos__isnull=False
    ).distinct().values_list("nombre", flat=True))})

    # 6. Predicción: Ana 3, Luis 2, María 1 y Pedro 0, incluyendo devueltos.
    resultados.append({"reto": 6, "resultado": list(Estudiante.objects.annotate(
        total_prestamos=Count("prestamos")).values("nombre", "total_prestamos"))})

    # 7. Predicción: Cien años de soledad, con tres préstamos entre sus copias.
    mas_prestado = Libro.objects.annotate(total_prestamos=Count("ejemplares__prestamos")).order_by(
        "-total_prestamos", "titulo", "pk").first()
    resultados.append({"reto": 7, "resultado": {"titulo": mas_prestado.titulo,
                       "total_prestamos": mas_prestado.total_prestamos}})

    # 8. Predicción: solo Pedro; los que ya devolvieron sí tienen historial.
    resultados.append({"reto": 8, "resultado": list(Estudiante.objects.filter(
        prestamos__isnull=True).values_list("nombre", flat=True))})

    # 9. Predicción: INV-001 se devuelve hoy y queda disponible; el historial sigue.
    prestamo = Prestamo.objects.get(ejemplar__codigo_inventario="INV-001", fecha_devolucion__isnull=True)
    prestamo.fecha_devolucion = timezone.localdate()
    prestamo.full_clean()
    prestamo.save(update_fields=["fecha_devolucion"])
    prestamo.refresh_from_db()
    resultados.append({"reto": 9, "resultado": {"ejemplar": prestamo.ejemplar.codigo_inventario,
                       "fecha_devolucion": prestamo.fecha_devolucion.isoformat(), "activo": prestamo.activo,
                       "disponible": disponibles.filter(pk=prestamo.ejemplar_id).exists()}})

    # 10. Predicción: se borra el autor de práctica y su enlace M2M; el libro permanece.
    pk_libro = libro.pk
    pk_autor = autor.pk
    autor.delete()
    resultados.append({"reto": 10, "resultado": {"autor_existe": Autor.objects.filter(pk=pk_autor).exists(),
                       "libro_existe": Libro.objects.filter(pk=pk_libro).exists(),
                       "autores_del_libro": list(libro.autores.values_list("nombre", flat=True)),
                       "copias_del_libro": libro.ejemplares.count()}})
    transaction.set_rollback(True)
    return resultados


def ejemplos_adicionales():
    """Q, aggregate, exclude y lookups adicionales del vocabulario de la fase 5."""
    return {
        "novela_o_ingenieria": list(Libro.objects.filter(
            Q(categoria__nombre="Novela") | Q(categoria__nombre="Ingeniería")
        ).values_list("titulo", flat=True)),
        "publicados_desde_2000": list(Libro.objects.filter(anio_publicacion__gte=2000).values_list("titulo", flat=True)),
        "publicados_antes_2000": list(Libro.objects.filter(anio_publicacion__lt=2000).values_list("titulo", flat=True)),
        "prestamos_totales": Prestamo.objects.aggregate(total=Count("pk")),
    }
