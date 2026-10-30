from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from moderation.services import set_hidden

from .models import Bookmark, Comment, Kudos


@admin.register(Kudos)
class KudosAdmin(admin.ModelAdmin):
    list_display = ["work", "user", "created_at"]
    raw_id_fields = ["work", "user"]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ["__str__", "created_at", "hidden_by_moderator"]
    list_filter = ["hidden_by_moderator"]
    search_fields = ["content", "pseud__name"]
    raw_id_fields = ["chapter", "parent", "pseud"]
    actions = ["hide", "unhide"]

    @admin.action(description=_("Ocultar comentários (moderação)"))
    def hide(self, request, queryset):
        for comment in queryset:
            set_hidden(comment, True, request.user)

    @admin.action(description=_("Reexibir comentários"))
    def unhide(self, request, queryset):
        for comment in queryset:
            set_hidden(comment, False, request.user)


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ["pseud", "work", "is_private", "is_rec", "created_at"]
    list_filter = ["is_private", "is_rec"]
    raw_id_fields = ["pseud", "work"]
    autocomplete_fields = ["tags"]
