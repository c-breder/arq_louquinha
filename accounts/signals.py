from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Pseud


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_default_pseud(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        Pseud.objects.create(user=instance, name=instance.username, is_default=True)


@receiver(post_delete, sender=Pseud)
def delete_avatar_file(sender, instance, **kwargs):
    if instance.avatar:
        instance.avatar.delete(save=False)
