from django.contrib import admin

from .models import Post, PostMedia, Story, Tag


class PostMediaInline(admin.TabularInline):
    model = PostMedia
    extra = 1


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "author", "privacy", "created_at")
    list_filter = ("privacy", "created_at")
    search_fields = ("author__email", "content")
    inlines = [PostMediaInline]


@admin.register(PostMedia)
class PostMediaAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "media_type", "uploaded_at")
    list_filter = ("media_type",)
    search_fields = ("post__content",)


@admin.register(Story)
class StoryAdmin(admin.ModelAdmin):
    list_display = ("id", "author", "created_at", "expires_at", "is_active")
    list_filter = ("created_at", "expires_at")
    search_fields = ("author__email",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_at")
    search_fields = ("name",)
