from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from accounts.models import Pseud
from tags.models import Tag
from works.models import Chapter, Work


class Kudos(models.Model):
    work = models.ForeignKey(Work, verbose_name=_("obra"), on_delete=models.CASCADE, related_name="kudos")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("usuário"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="kudos",
    )
    # Visitante: hash da sessão (1 kudos por sessão por obra)
    guest_key = models.CharField(_("chave do visitante"), max_length=64, blank=True)
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        verbose_name = _("kudos")
        verbose_name_plural = _("kudos")
        constraints = [
            models.UniqueConstraint(
                fields=["work", "user"], condition=models.Q(user__isnull=False), name="kudos_unique_user"
            ),
            models.UniqueConstraint(
                fields=["work", "guest_key"], condition=~models.Q(guest_key=""), name="kudos_unique_guest"
            ),
            models.CheckConstraint(
                condition=models.Q(user__isnull=False) | ~models.Q(guest_key=""),
                name="kudos_has_owner",
            ),
        ]

    def __str__(self):
        return f"{self.user or _('visitante')} → {self.work}"


class Comment(models.Model):
    chapter = models.ForeignKey(
        Chapter, verbose_name=_("capítulo"), on_delete=models.CASCADE, related_name="comments"
    )
    parent = models.ForeignKey(
        "self",
        verbose_name=_("resposta a"),
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    # SET_NULL: o comentário fica como "conta excluída"
    pseud = models.ForeignKey(
        Pseud, verbose_name=_("pseudônimo"), null=True, on_delete=models.SET_NULL, related_name="comments"
    )
    content = models.TextField(_("texto"))
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    edited_at = models.DateTimeField(_("editado em"), null=True, blank=True)
    hidden_by_moderator = models.BooleanField(_("oculto pela moderação"), default=False)
    # Apagado mas com respostas: fica o lugar na conversa, sem o texto
    deleted = models.BooleanField(_("apagado"), default=False)

    class Meta:
        verbose_name = _("comentário")
        verbose_name_plural = _("comentários")
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["chapter", "created_at"]),
        ]

    def __str__(self):
        return f"{self.pseud} @ {self.chapter}"


class Bookmark(models.Model):
    pseud = models.ForeignKey(
        Pseud, verbose_name=_("pseudônimo"), on_delete=models.CASCADE, related_name="bookmarks"
    )
    work = models.ForeignKey(Work, verbose_name=_("obra"), on_delete=models.CASCADE, related_name="bookmarks")
    notes = models.TextField(_("notas"), blank=True)
    tags = models.ManyToManyField(Tag, verbose_name=_("tags"), blank=True, related_name="bookmarks")
    is_private = models.BooleanField(_("privado"), default=False)
    is_rec = models.BooleanField(_("recomendação"), default=False)
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("bookmark")
        verbose_name_plural = _("bookmarks")
        constraints = [
            models.UniqueConstraint(fields=["pseud", "work"], name="bookmark_unique"),
        ]

    def __str__(self):
        return f"{self.pseud} → {self.work}"
