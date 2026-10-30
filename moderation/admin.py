from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from . import services
from .models import ModerationAction, Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["__str__", "target_link", "reporter", "status", "created_at", "handled_by"]
    list_filter = ["status", "reason", "content_type"]
    raw_id_fields = ["reporter", "handled_by"]
    readonly_fields = ["created_at", "target_link"]
    actions = ["hide_targets", "unhide_targets", "suspend_owners", "mark_resolved", "dismiss"]

    @admin.display(description=_("conteúdo"))
    def target_link(self, report):
        target = report.target
        if target is None:
            return _("(apagado)")
        return format_html("{}", str(target)[:80])

    def _each(self, request, queryset, apply, success):
        done = 0
        for report in queryset.select_related("content_type"):
            if report.target is not None:
                done += bool(apply(report))
        self.message_user(request, success % {"count": done}, messages.SUCCESS)

    @admin.action(description=_("Ocultar o conteúdo denunciado"))
    def hide_targets(self, request, queryset):
        def apply(report):
            changed = services.set_hidden(report.target, True, request.user, report=report)
            services.close_report(report, request.user, Report.Status.RESOLVED)
            return changed

        self._each(request, queryset, apply, _("%(count)d conteúdo(s) ocultado(s)."))

    @admin.action(description=_("Reexibir o conteúdo denunciado"))
    def unhide_targets(self, request, queryset):
        self._each(
            request,
            queryset,
            lambda report: services.set_hidden(report.target, False, request.user, report=report),
            _("%(count)d conteúdo(s) reexibido(s)."),
        )

    @admin.action(description=_("Suspender quem publicou"))
    def suspend_owners(self, request, queryset):
        def apply(report):
            changed = sum(
                services.set_suspended(owner, True, request.user, report=report)
                for owner in services.owners_of(report.target)
            )
            services.close_report(report, request.user, Report.Status.RESOLVED)
            return changed

        self._each(request, queryset, apply, _("%(count)d denúncia(s) com conta suspensa."))

    @admin.action(description=_("Marcar como resolvida"))
    def mark_resolved(self, request, queryset):
        for report in queryset:
            services.close_report(report, request.user, Report.Status.RESOLVED)
        self.message_user(request, _("Denúncias resolvidas."), messages.SUCCESS)

    @admin.action(description=_("Descartar (sem problema)"))
    def dismiss(self, request, queryset):
        for report in queryset:
            services.close_report(report, request.user, Report.Status.DISMISSED)
        self.message_user(request, _("Denúncias descartadas."), messages.SUCCESS)


@admin.register(ModerationAction)
class ModerationActionAdmin(admin.ModelAdmin):
    list_display = ["created_at", "actor", "action", "content_type", "object_id", "note"]
    list_filter = ["action", "content_type"]
    search_fields = ["note", "actor__username"]

    # Histórico só para leitura
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
