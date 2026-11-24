from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # first_name / last_name do not exist on this model.
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Kişisel bilgi", {"fields": ("email",)}),
        ("Yetkiler", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Önemli tarihler", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "password1", "password2"),
        }),
    )
    list_display = ("username", "email", "is_staff", "date_joined")
    search_fields = ("username", "email")
    ordering = ("-date_joined",)
