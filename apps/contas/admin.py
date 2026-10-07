from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import PerfilAcessibilidade, Usuario


class PerfilAcessibilidadeInline(admin.StackedInline):
    model = PerfilAcessibilidade
    can_delete = False
    extra = 0


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    ordering = ["first_name", "last_name"]
    list_display = ["email", "first_name", "last_name", "papel", "unidade", "is_active"]
    list_filter = ["papel", "unidade", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    inlines = [PerfilAcessibilidadeInline]
    fieldsets = [
        (None, {"fields": ["email", "password"]}),
        ("Dados pessoais", {"fields": ["first_name", "last_name"]}),
        ("Acesso", {"fields": ["papel", "unidade", "is_active", "is_staff", "is_superuser", "groups"]}),
        ("Datas", {"fields": ["last_login", "date_joined"]}),
    ]
    add_fieldsets = [
        (
            None,
            {
                "classes": ["wide"],
                "fields": ["email", "first_name", "last_name", "papel", "unidade", "password1", "password2"],
            },
        ),
    ]
