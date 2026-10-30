from django.contrib import admin

from .models import Collection, CollectionItem, Prompt


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ["title", "slug", "kind", "owner", "is_open", "is_moderated", "closes_at"]
    list_filter = ["kind", "is_open", "is_moderated"]
    search_fields = ["title", "slug"]
    raw_id_fields = ["owner", "moderators"]


@admin.register(CollectionItem)
class CollectionItemAdmin(admin.ModelAdmin):
    list_display = ["work", "collection", "status", "created_at"]
    list_filter = ["status"]
    raw_id_fields = ["work", "collection", "prompt", "added_by"]


@admin.register(Prompt)
class PromptAdmin(admin.ModelAdmin):
    list_display = ["__str__", "collection", "author", "created_at"]
    raw_id_fields = ["collection", "author"]
