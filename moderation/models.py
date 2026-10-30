from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _


class Report(models.Model):
    class Reason(models.TextChoices):
        SPAM = "spam", _("Spam")
        HARASSMENT = "harassment", _("Assédio ou ataque")
        WRONG_RATING = "wrong_rating", _("Classificação, avisos ou tags incorretos")
        PLAGIARISM = "plagiarism", _("Plágio ou violação de direitos autorais")
        ILLEGAL = "illegal", _("Conteúdo ilegal")
        OTHER = "other", _("Outro motivo")

    class Status(models.TextChoices):
        OPEN = "open", _("Aberta")
        RESOLVED = "resolved", _("Resolvida")
        DISMISSED = "dismissed", _("Descartada")

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("denunciante"),
        null=True,
        on_delete=models.SET_NULL,
        related_name="reports_made",
    )
    # Alvo genérico: obra, capítulo, comentário, imagem, perfil ou mensagem
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    reason = models.CharField(_("motivo"), max_length=20, choices=Reason.choices)
    details = models.TextField(_("detalhes"), blank=True)
    status = models.CharField(_("situação"), max_length=10, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(_("criada em"), auto_now_add=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("tratada por"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reports_handled",
    )
    handled_at = models.DateTimeField(_("tratada em"), null=True, blank=True)
    resolution_note = models.TextField(_("observação da moderação"), blank=True)

    class Meta:
        verbose_name = _("denúncia")
        verbose_name_plural = _("denúncias")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.get_reason_display()} – {self.content_type} #{self.object_id}"


class ModerationAction(models.Model):
    # Histórico de tudo que a moderação fez
    class Action(models.TextChoices):
        APPROVE_ACCOUNT = "approve_account", _("Aprovou conta")
        REJECT_ACCOUNT = "reject_account", _("Recusou conta")
        CHANGE_MEDIA_LEVEL = "change_media_level", _("Mudou nível de mídia")
        HIDE = "hide", _("Ocultou")
        UNHIDE = "unhide", _("Reexibiu")
        REMOVE = "remove", _("Removeu")
        WARN = "warn", _("Advertiu")
        SUSPEND = "suspend", _("Suspendeu")
        UNSUSPEND = "unsuspend", _("Retirou suspensão")
        TAG_CANONIZE = "tag_canonize", _("Tornou tag canônica")
        TAG_DECANONIZE = "tag_decanonize", _("Tirou tag de canônica")
        TAG_MERGE = "tag_merge", _("Tornou tag sinônimo")
        TAG_UNMERGE = "tag_unmerge", _("Desfez sinônimo")
        TAG_ADD_META = "tag_add_meta", _("Adicionou metatag")
        TAG_REMOVE_META = "tag_remove_meta", _("Removeu metatag")
        TAG_ADD_FANDOM = "tag_add_fandom", _("Ligou tag a fandom")
        TAG_REMOVE_FANDOM = "tag_remove_fandom", _("Desligou tag de fandom")

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("moderador"),
        null=True,
        on_delete=models.SET_NULL,
        related_name="moderation_actions",
    )
    action = models.CharField(_("ação"), max_length=30, choices=Action.choices)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    report = models.ForeignKey(
        Report, verbose_name=_("denúncia"), null=True, blank=True, on_delete=models.SET_NULL, related_name="actions"
    )
    note = models.TextField(_("observação"), blank=True)
    created_at = models.DateTimeField(_("feita em"), auto_now_add=True)

    class Meta:
        verbose_name = _("ação de moderação")
        verbose_name_plural = _("histórico de moderação")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.actor} – {self.get_action_display()}"
