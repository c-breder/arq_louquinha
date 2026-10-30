from django.contrib import admin

from .models import MetaTagging, Tag


class SubTagInline(admin.TabularInline):
    model = MetaTagging
    fk_name = "meta"
    extra = 0
    raw_id_fields = ["sub"]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "type", "canonical", "merger", "use_count"]
    list_filter = ["type", "canonical"]
    search_fields = ["name"]
    autocomplete_fields = ["merger", "fandoms"]
    list_select_related = ["merger"]
    inlines = [SubTagInline]


@admin.register(MetaTagging)
class MetaTaggingAdmin(admin.ModelAdmin):
    list_display = ["meta", "sub"]
    search_fields = ["meta__name", "sub__name"]
    raw_id_fields = ["meta", "sub"]
