from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Follow, Friendship, Profile, User


class UserAdmin(BaseUserAdmin):
    model = User
    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_superuser",
        "status",
        "is_verified",
    )
    list_filter = ("is_staff", "is_superuser", "status", "is_verified")
    search_fields = ("email", "first_name", "last_name", "username")
    ordering = ("email",)
    readonly_fields = ("date_joined", "last_seen", "last_login_ip")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal Info",
            {"fields": ("first_name", "last_name", "username", "phone_number")},
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_verified",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Status", {"fields": ("status",)}),
        ("Activity", {"fields": ("last_login_ip", "last_seen", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_superuser",
                    "status",
                ),
            },
        ),
    )


admin.site.register(User, UserAdmin)
admin.site.register(Profile)
admin.site.register(Follow)
admin.site.register(Friendship)
