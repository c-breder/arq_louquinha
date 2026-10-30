from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from tags.wrangling import WRANGLERS_GROUP

from . import services
from .models import PreApprovedEmail, Pseud, User


class PseudInline(admin.TabularInline):
    model = Pseud
    extra = 0
    fields = ["name", "is_default", "description"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["username", "email", "is_approved", "media_level", "is_active", "date_joined"]
    list_filter = ["is_approved", "media_level", "is_active", "is_staff", "date_joined"]
    search_fields = ["username", "email"]
    ordering = ["-date_joined"]
    readonly_fields = ["approved_at", "approved_by", "adult_confirmed_at", "last_login", "date_joined"]
    inlines = [PseudInline]
    actions = ["approve_users", "reject_users", "set_media_basic", "set_media_images", "grant_wrangler", "revoke_wrangler"]
    fieldsets = BaseUserAdmin.fieldsets + (
        (_("Aprovação"), {"fields": ["is_approved", "approved_at", "approved_by", "adult_confirmed_at"]}),
        (_("Mídia e preferências"), {"fields": ["media_level", "language", "hide_warnings", "hide_explicit"]}),
    )

    @admin.action(description=_("Aprovar contas selecionadas"))
    def approve_users(self, request, queryset):
        count = sum(services.approve_user(user, request.user) for user in queryset)
        self.message_user(
            request,
            ngettext("%d conta aprovada.", "%d contas aprovadas.", count) % count,
            messages.SUCCESS,
        )

    @admin.action(description=_("Recusar contas selecionadas (desativa)"))
    def reject_users(self, request, queryset):
        count = 0
        for user in queryset.exclude(pk=request.user.pk):
            services.reject_user(user, request.user)
            count += 1
        self.message_user(
            request,
            ngettext("%d conta recusada.", "%d contas recusadas.", count) % count,
            messages.WARNING,
        )

    def _set_media_level(self, request, queryset, level):
        count = sum(services.set_media_level(user, level, request.user) for user in queryset)
        self.message_user(
            request,
            ngettext("Nível de mídia alterado em %d conta.", "Nível de mídia alterado em %d contas.", count)
            % count,
            messages.SUCCESS,
        )

    @admin.action(description=_("Dar papel de wrangler"))
    def grant_wrangler(self, request, queryset):
        group, _created = Group.objects.get_or_create(name=WRANGLERS_GROUP)
        for user in queryset:
            user.groups.add(group)
        self.message_user(request, _("Papel de wrangler concedido."), messages.SUCCESS)

    @admin.action(description=_("Retirar papel de wrangler"))
    def revoke_wrangler(self, request, queryset):
        group = Group.objects.filter(name=WRANGLERS_GROUP).first()
        if group:
            for user in queryset:
                user.groups.remove(group)
        self.message_user(request, _("Papel de wrangler retirado."), messages.SUCCESS)

    @admin.action(description=_("Nível de mídia: Básico"))
    def set_media_basic(self, request, queryset):
        self._set_media_level(request, queryset, User.MediaLevel.BASIC)

    @admin.action(description=_("Nível de mídia: Imagens"))
    def set_media_images(self, request, queryset):
        self._set_media_level(request, queryset, User.MediaLevel.IMAGES)


@admin.register(PreApprovedEmail)
class PreApprovedEmailAdmin(admin.ModelAdmin):
    list_display = ["email", "media_level", "note", "used_by", "used_at", "created_by", "created_at"]
    list_filter = ["media_level", ("used_at", admin.EmptyFieldListFilter)]
    search_fields = ["email", "note"]
    fields = ["email", "media_level", "note", "created_by", "created_at", "used_by", "used_at"]
    readonly_fields = ["created_by", "created_at", "used_by", "used_at"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Pseud)
class PseudAdmin(admin.ModelAdmin):
    list_display = ["name", "user", "is_default", "created_at"]
    search_fields = ["name", "user__username"]
    list_select_related = ["user"]
    raw_id_fields = ["user"]
