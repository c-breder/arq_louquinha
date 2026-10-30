from django.apps import AppConfig
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


def create_wranglers_group(sender, **kwargs):
    from django.contrib.auth.models import Group, Permission

    from .wrangling import WRANGLERS_GROUP

    permission = Permission.objects.filter(codename="wrangle", content_type__app_label="tags").first()
    if permission:
        group, _created = Group.objects.get_or_create(name=WRANGLERS_GROUP)
        group.permissions.add(permission)


class TagsConfig(AppConfig):
    name = "tags"
    verbose_name = _("Tags")

    def ready(self):
        from django.db.models import CharField
        from django.db.models.functions import Lower

        # Permite name__lower=..., que usa o índice único em Lower(name)
        CharField.register_lookup(Lower)
        post_migrate.connect(create_wranglers_group, sender=self)
