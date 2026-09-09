from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("Roles", {"fields": ("is_student", "is_supervisor")}),
    )
    list_display = ("username", "email", "is_staff", "is_supervisor", "is_student", "is_active")
    list_filter = ("is_staff", "is_supervisor", "is_student", "is_superuser", "is_active")
