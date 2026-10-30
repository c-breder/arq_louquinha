from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import WorkImage


@receiver(post_delete, sender=WorkImage)
def delete_image_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
