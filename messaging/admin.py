from django.contrib import admin

from .models import Message


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    # Mensagens são privadas: o admin só vê as que foram denunciadas
    list_display = ["pk", "sender", "created_at", "hidden_by_moderator"]
    list_filter = ["hidden_by_moderator"]
    raw_id_fields = ["conversation", "sender"]

    def get_queryset(self, request):
        from django.contrib.contenttypes.models import ContentType

        from moderation.models import Report

        reported = Report.objects.filter(content_type=ContentType.objects.get_for_model(Message)).values("object_id")
        return super().get_queryset(request).filter(pk__in=reported)

    def has_add_permission(self, request):
        return False
