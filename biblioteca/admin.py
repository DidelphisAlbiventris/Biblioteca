from django.contrib import admin, messages
from django.db.models import Count, Exists, OuterRef
from django.utils import timezone

from .models import Autor, Categoria, Ejemplar, Estudiante, Libro, Prestamo

admin.site.site_header = "Biblioteca UFPS"
admin.site.site_title = "Biblioteca UFPS"
admin.site.index_title = "Catálogo, inventario y préstamos"
admin.site.empty_value_display = "—"


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "descripcion")
    search_fields = ("nombre", "descripcion")
    list_filter = ("nombre",)


@admin.register(Autor)
class AutorAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)
    list_filter = ("libros__categoria",)


class EjemplarInline(admin.TabularInline):
    model = Ejemplar
    extra = 1
    fields = ("codigo_inventario", "condicion", "nota")
    show_change_link = True


@admin.register(Libro)
class LibroAdmin(admin.ModelAdmin):
    list_display = ("titulo", "isbn", "anio_publicacion", "idioma", "categoria", "lista_autores", "total_copias")
    search_fields = ("titulo", "isbn", "autores__nombre")
    list_filter = ("categoria", "idioma", "anio_publicacion")
    autocomplete_fields = ("categoria", "autores")
    inlines = (EjemplarInline,)
    list_select_related = ("categoria",)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("autores").annotate(
            numero_copias=Count("ejemplares", distinct=True)
        )

    @admin.display(description="Autores")
    def lista_autores(self, obj):
        return ", ".join(autor.nombre for autor in obj.autores.all()) or "Sin autores registrados"

    @admin.display(description="Copias físicas", ordering="numero_copias")
    def total_copias(self, obj):
        return obj.numero_copias


@admin.register(Ejemplar)
class EjemplarAdmin(admin.ModelAdmin):
    list_display = ("codigo_inventario", "libro", "condicion", "disponible")
    search_fields = ("codigo_inventario", "libro__titulo", "libro__isbn")
    list_filter = ("condicion", "libro__categoria")
    autocomplete_fields = ("libro",)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("libro").annotate(
            tiene_prestamo_activo=Exists(Prestamo.objects.filter(
                ejemplar_id=OuterRef("pk"), fecha_devolucion__isnull=True
            ))
        )

    @admin.display(boolean=True, description="Disponible")
    def disponible(self, obj):
        return not obj.tiene_prestamo_activo


@admin.register(Estudiante)
class EstudianteAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "correo", "creado_en")
    search_fields = ("codigo", "nombre", "correo")
    list_filter = ("creado_en",)
    readonly_fields = ("creado_en",)


class EstadoPrestamoFilter(admin.SimpleListFilter):
    title = "estado del préstamo"
    parameter_name = "estado"

    def lookups(self, request, model_admin):
        return [("activo", "Sin devolver"), ("vencido", "Vencido"), ("devuelto", "Devuelto")]

    def queryset(self, request, queryset):
        if self.value() == "activo":
            return queryset.filter(fecha_devolucion__isnull=True)
        if self.value() == "vencido":
            return queryset.filter(fecha_devolucion__isnull=True, fecha_limite__lt=timezone.localdate())
        if self.value() == "devuelto":
            return queryset.filter(fecha_devolucion__isnull=False)
        return queryset


@admin.register(Prestamo)
class PrestamoAdmin(admin.ModelAdmin):
    list_display = ("ejemplar", "estudiante", "fecha_salida", "fecha_limite", "fecha_devolucion", "sin_devolver")
    search_fields = ("estudiante__codigo", "estudiante__nombre", "ejemplar__codigo_inventario", "ejemplar__libro__titulo")
    list_filter = (EstadoPrestamoFilter, "fecha_salida", "fecha_limite", "ejemplar__libro__categoria")
    autocomplete_fields = ("estudiante", "ejemplar")
    list_select_related = ("estudiante", "ejemplar__libro")
    date_hierarchy = "fecha_salida"
    actions = ("marcar_devueltos",)
    fieldsets = (
        ("¿Quién recibe qué copia?", {"fields": ("estudiante", "ejemplar")}),
        ("Fechas del préstamo", {"fields": ("fecha_salida", "fecha_limite", "fecha_devolucion"),
          "description": "Deja la devolución vacía mientras la copia siga prestada."}),
    )

    @admin.display(boolean=True, description="Sin devolver")
    def sin_devolver(self, obj):
        return obj.activo

    @admin.action(description="Marcar préstamos seleccionados como devueltos hoy", permissions=["change"])
    def marcar_devueltos(self, request, queryset):
        hoy = timezone.localdate()
        cantidad = queryset.filter(fecha_devolucion__isnull=True, fecha_salida__lte=hoy).update(fecha_devolucion=hoy)
        self.message_user(request, f"Préstamos marcados como devueltos: {cantidad}. Los ya devueltos conservan su fecha.", messages.SUCCESS)
