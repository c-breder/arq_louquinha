from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    class MediaLevel(models.IntegerChoices):
        BASIC = 0, _("Básico (só avatar)")
        IMAGES = 1, _("Imagens (avatar e imagens no texto)")

    email = models.EmailField(_("e-mail"), unique=True)
    is_approved = models.BooleanField(_("aprovada"), default=False)
    approved_at = models.DateTimeField(_("aprovada em"), null=True, blank=True)
    approved_by = models.ForeignKey(
        "self",
        verbose_name=_("aprovada por"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    adult_confirmed_at = models.DateTimeField(_("confirmou 18+ em"), null=True, blank=True)
    media_level = models.PositiveSmallIntegerField(
        _("nível de mídia"), choices=MediaLevel.choices, default=MediaLevel.BASIC
    )
    language = models.CharField(
        _("idioma da interface"),
        max_length=10,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
    )
    hide_warnings = models.BooleanField(_("esconder avisos"), default=False)
    hide_explicit = models.BooleanField(_("ocultar obras explícitas"), default=False)
    allow_messages = models.BooleanField(_("aceitar mensagens privadas"), default=True)

    class Meta:
        verbose_name = _("usuário")
        verbose_name_plural = _("usuários")

    def save(self, *args, **kwargs):
        # Superusuário já nasce aprovado
        if self.is_superuser and not self.is_approved:
            self.is_approved = True
            self.approved_at = self.approved_at or timezone.now()
        super().save(*args, **kwargs)

    @property
    def default_pseud(self):
        return self.pseuds.filter(is_default=True).first()

    @property
    def can_upload_images(self):
        return self.media_level >= self.MediaLevel.IMAGES


class Pseud(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("usuário"),
        on_delete=models.CASCADE,
        related_name="pseuds",
    )
    name = models.CharField(_("nome"), max_length=60)
    description = models.TextField(_("descrição"), blank=True)
    avatar = models.ImageField(_("avatar"), upload_to="avatares/", blank=True)
    is_default = models.BooleanField(_("padrão"), default=False)
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        verbose_name = _("pseudônimo")
        verbose_name_plural = _("pseudônimos")
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint("user", Lower("name"), name="pseud_name_unique_per_user"),
            models.UniqueConstraint(
                fields=["user"],
                condition=models.Q(is_default=True),
                name="pseud_one_default_per_user",
            ),
        ]

    def __str__(self):
        if self.name == self.user.username:
            return self.name
        return f"{self.name} ({self.user.username})"
