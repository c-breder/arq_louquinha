import re

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class SiteSettings(models.Model):
    """Configurações que a equipe muda pelo admin, sem mexer no .env nem reiniciar o site (registro único)."""

    open_signup_until = models.DateTimeField(
        _("aprovar novas contas automaticamente até"),
        null=True,
        blank=True,
        help_text=_("Enquanto essa data não passar, quem criar conta e confirmar o e-mail já entra aprovado. "
                    "Deixe em branco para fechar."),
    )
    notify_emails = models.TextField(
        _("avisar destes e-mails a cada conta criada"),
        blank=True,
        help_text=_("Um e-mail por linha (ou separados por vírgula)."),
    )
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("configurações do site")
        verbose_name_plural = _("configurações do site")

    def __str__(self):
        return str(_("Configurações do site"))

    @classmethod
    def current(cls):
        settings, _created = cls.objects.get_or_create(pk=1)
        return settings

    @property
    def signup_window_open(self):
        return bool(self.open_signup_until and timezone.now() < self.open_signup_until)

    @property
    def notify_list(self):
        return [email for email in re.split(r"[\s,;]+", self.notify_emails) if "@" in email]
