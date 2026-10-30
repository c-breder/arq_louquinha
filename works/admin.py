from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from moderation.services import set_hidden

from .models import Chapter, Series, SeriesWork, Work, WorkAuthor, WorkImage


@admin.register(WorkImage)
class WorkImageAdmin(admin.ModelAdmin):
    list_display = ["file", "owner", "width", "height", "size", "created_at"]
    raw_id_fields = ["owner"]
    readonly_fields = ["width", "height", "size", "created_at"]


class WorkAuthorInline(admin.TabularInline):
    model = WorkAuthor
    extra = 0
    raw_id_fields = ["pseud", "invited_by"]


class ChapterInline(admin.StackedInline):
    model = Chapter
    extra = 0
    fields = ["position", "title", "status", "word_count", "published_at"]
    readonly_fields = ["word_count"]
    show_change_link = True


@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    list_display = ["title", "rating", "language", "status", "word_count", "published_at", "hidden_by_moderator"]
    list_filter = ["status", "rating", "language", "is_complete", "restricted", "hidden_by_moderator"]
    search_fields = ["title", "authorships__pseud__name"]
    autocomplete_fields = ["tags"]
    readonly_fields = ["word_count", "hit_count", "created_at", "updated_at"]
    date_hierarchy = "published_at"
    inlines = [WorkAuthorInline, ChapterInline]
    actions = ["hide", "unhide"]

    @admin.action(description=_("Ocultar obras (moderação)"))
    def hide(self, request, queryset):
        for work in queryset:
            set_hidden(work, True, request.user)

    @admin.action(description=_("Reexibir obras"))
    def unhide(self, request, queryset):
        for work in queryset:
            set_hidden(work, False, request.user)


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ["__str__", "work", "position", "status", "word_count"]
    list_filter = ["status"]
    search_fields = ["title", "work__title"]
    raw_id_fields = ["work"]
    readonly_fields = ["word_count", "created_at", "updated_at"]


class SeriesWorkInline(admin.TabularInline):
    model = SeriesWork
    extra = 0
    raw_id_fields = ["work"]


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = ["title", "is_complete", "updated_at"]
    search_fields = ["title"]
    raw_id_fields = ["pseuds"]
    inlines = [SeriesWorkInline]
