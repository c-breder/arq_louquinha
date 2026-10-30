from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ChallengesConfig(AppConfig):
    name = "challenges"
    verbose_name = _("Coleções e desafios")
