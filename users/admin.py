from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import BlockedUser, Follow, Friendship, Profile, User, UserSettings


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'is_staff', 'is_active', 'status', 'last_seen')
    list_filter = ('is_staff', 'is_active', 'status', 'is_verified')
    search_fields = ('email', 'first_name', 'last_name', 'username')
    ordering = ('-date_joined',)
    
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal Info'), {'fields': ('first_name', 'last_name', 'username', 'phone_number')}),
        (_('Status'), {'fields': ('status', 'is_verified', 'last_login_ip', 'last_seen')}),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2'),
        }),
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'location', 'followers_count', 'following_count', 'friends_count')
    list_select_related = ('user',)
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'bio', 'location')
    raw_id_fields = ('user',)


@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ('user', 'profile_visibility', 'theme', 'email_notifications')
    list_select_related = ('user',)
    search_fields = ('user__email', 'user__first_name', 'user__last_name')
    raw_id_fields = ('user',)


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ('requester', 'receiver', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('requester__email', 'receiver__email')
    raw_id_fields = ('requester', 'receiver')


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ('follower', 'following', 'created_at')
    search_fields = ('follower__email', 'following__email')
    raw_id_fields = ('follower', 'following')


@admin.register(BlockedUser)
class BlockedUserAdmin(admin.ModelAdmin):
    list_display = ('blocker', 'blocked', 'created_at', 'reason')
    search_fields = ('blocker__email', 'blocked__email', 'reason')
    raw_id_fields = ('blocker', 'blocked')


# Optional: Custom admin site title
admin.site.site_header = "IGSSAX Administration"
admin.site.site_title = "IGSSAX Admin Portal"
admin.site.index_title = "Welcome to IGSSAX Admin"