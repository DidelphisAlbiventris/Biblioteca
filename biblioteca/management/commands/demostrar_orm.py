import json

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from biblioteca.consultas import ejecutar_retos, ejemplos_adicionales, medir_consultas
from biblioteca.models import Categoria, Prestamo


class Command(BaseCommand):
    help = "Ejecuta los diez retos sin conservar sus cambios y mide el problema N+1 en los datos actuales."

    def handle(self, *args, **options):
        if not Categoria.objects.filter(nombre="Novela").exists() or not Prestamo.objects.filter(
            ejemplar__codigo_inventario="INV-001", fecha_devolucion__isnull=True
        ).exists():
            raise CommandError("Ejecuta datos_demo en una base de práctica con INV-001 aún prestado.")
        mediciones = medir_consultas()
        try:
            retos = ejecutar_retos()
        except IntegrityError as exc:
            raise CommandError("El ISBN o los códigos de práctica ya existen. Usa una base de práctica; se revirtieron los cambios.") from exc
        self.stdout.write(json.dumps({"retos": retos, "optimizacion": mediciones,
                                      "ejemplos_adicionales": ejemplos_adicionales()}, ensure_ascii=False, indent=2))
