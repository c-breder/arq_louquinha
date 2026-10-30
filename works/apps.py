from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WorksConfig(AppConfig):
    name = "works"
    verbose_name = _("Obras")

    def ready(self):
        from . import signals  # noqa: F401
