"""Seis entidades: catálogo, inventario físico y préstamos con historial."""
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Categoria(models.Model):
    nombre = models.CharField("nombre", max_length=80, unique=True)
    descripcion = models.TextField("descripción", blank=True)

    class Meta:
        ordering = ["nombre"]
        verbose_name = "categoría"
        verbose_name_plural = "categorías"

    def __str__(self):
        return self.nombre


class Autor(models.Model):
    nombre = models.CharField("nombre", max_length=150)

    class Meta:
        ordering = ["nombre", "pk"]
        verbose_name = "autor"
        verbose_name_plural = "autores"

    def __str__(self):
        return self.nombre


class Libro(models.Model):
    titulo = models.CharField("título", max_length=200)
    anio_publicacion = models.PositiveSmallIntegerField(
        "año de publicación", validators=[MinValueValidator(1)]
    )
    isbn = models.CharField(
        "ISBN", max_length=13, unique=True,
        validators=[RegexValidator(
            r"^(?:[0-9]{9}[0-9X]|[0-9]{13})$",
            "Escribe un ISBN de 10 o 13 caracteres, sin espacios ni guiones.",
        )],
    )
    categoria = models.ForeignKey(
        Categoria, verbose_name="categoría", on_delete=models.PROTECT, related_name="libros"
    )
    autores = models.ManyToManyField(Autor, verbose_name="autores", related_name="libros")
    idioma = models.CharField("idioma", max_length=40, default="Español")

    class Meta:
        ordering = ["titulo", "pk"]
        verbose_name = "libro"
        constraints = [models.CheckConstraint(
            condition=Q(anio_publicacion__gte=1), name="libro_anio_positivo"
        )]

    def __str__(self):
        return f"{self.titulo} (ISBN {self.isbn})"


class Ejemplar(models.Model):
    class Condicion(models.TextChoices):
        NUEVO = "nuevo", "Nuevo"
        USADO = "usado", "Usado"
        DANADO = "danado", "Dañado"

    libro = models.ForeignKey(
        Libro, verbose_name="libro", on_delete=models.PROTECT, related_name="ejemplares"
    )
    codigo_inventario = models.CharField("código de inventario", max_length=30, unique=True)
    condicion = models.CharField(
        "condición", max_length=10, choices=Condicion.choices, default=Condicion.NUEVO
    )
    nota = models.TextField("nota sobre su condición", blank=True)

    class Meta:
        ordering = ["codigo_inventario"]
        verbose_name = "copia física"
        verbose_name_plural = "copias físicas"
        constraints = [models.CheckConstraint(
            condition=Q(condicion__in=["nuevo", "usado", "danado"]),
            name="ejemplar_condicion_valida",
        )]

    def __str__(self):
        return f"{self.codigo_inventario} — {self.libro.titulo} ({self.get_condicion_display()})"


class Estudiante(models.Model):
    codigo = models.CharField("código estudiantil", max_length=20, unique=True)
    nombre = models.CharField("nombre", max_length=150)
    correo = models.EmailField("correo electrónico", unique=True)
    creado_en = models.DateTimeField("fecha de registro", auto_now_add=True)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "estudiante"

    def __str__(self):
        return f"{self.codigo} — {self.nombre}"


class Prestamo(models.Model):
    ejemplar = models.ForeignKey(
        Ejemplar, verbose_name="copia física", on_delete=models.PROTECT, related_name="prestamos"
    )
    estudiante = models.ForeignKey(
        Estudiante, verbose_name="estudiante", on_delete=models.PROTECT, related_name="prestamos"
    )
    fecha_salida = models.DateField("fecha de salida", default=timezone.localdate)
    fecha_limite = models.DateField("fecha límite de devolución")
    fecha_devolucion = models.DateField("fecha real de devolución", null=True, blank=True)

    class Meta:
        ordering = ["-fecha_salida", "-pk"]
        verbose_name = "préstamo"
        verbose_name_plural = "préstamos"
        constraints = [
            models.UniqueConstraint(
                fields=["ejemplar"], condition=Q(fecha_devolucion__isnull=True),
                name="un_prestamo_activo_por_ejemplar",
                violation_error_message="Esta copia ya tiene un préstamo activo.",
            ),
            models.CheckConstraint(
                condition=Q(fecha_limite__gte=F("fecha_salida")),
                name="prestamo_limite_desde_salida",
            ),
            models.CheckConstraint(
                condition=Q(fecha_devolucion__isnull=True) | Q(fecha_devolucion__gte=F("fecha_salida")),
                name="prestamo_devolucion_desde_salida",
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.fecha_salida and self.fecha_limite and self.fecha_limite < self.fecha_salida:
            errors["fecha_limite"] = "La fecha límite no puede ser anterior a la salida."
        if self.fecha_salida and self.fecha_devolucion and self.fecha_devolucion < self.fecha_salida:
            errors["fecha_devolucion"] = "La devolución no puede ser anterior a la salida."
        if self.ejemplar_id and self.fecha_devolucion is None:
            activos = Prestamo.objects.filter(ejemplar_id=self.ejemplar_id, fecha_devolucion__isnull=True)
            if self.pk:
                activos = activos.exclude(pk=self.pk)
            if activos.exists():
                errors["ejemplar"] = "Esta copia ya tiene un préstamo activo. Registra primero su devolución."
        if errors:
            raise ValidationError(errors)

    @property
    def activo(self):
        return self.fecha_devolucion is None

    def __str__(self):
        estado = "activo" if self.activo else "devuelto"
        return f"{self.ejemplar.codigo_inventario} → {self.estudiante.nombre} ({estado})"
