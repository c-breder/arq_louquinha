from django.contrib import admin
from django.db import models
from django.shortcuts import redirect
from django.urls import reverse

from .models import SiteSettings


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    fields = ["auto_approve_signups", "open_signup_until", "notify_emails", "direct_url", "updated_at"]
    readonly_fields = ["updated_at"]
    # Endereço digitado sem esquema vira https://
    formfield_overrides = {models.URLField: {"assume_scheme": "https"}}

    # Registro único: a lista leva direto para a tela de edição
    def changelist_view(self, request, extra_context=None):
        settings = SiteSettings.current()
        return redirect(reverse("admin:core_sitesettings_change", args=[settings.pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
