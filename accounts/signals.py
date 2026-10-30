from allauth.account.signals import email_confirmed, user_signed_up
from django.conf import settings
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.urls import reverse

from .models import Pseud


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_default_pseud(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        Pseud.objects.create(user=instance, name=instance.username, is_default=True)


@receiver(post_delete, sender=Pseud)
def delete_avatar_file(sender, instance, **kwargs):
    if instance.avatar:
        instance.avatar.delete(save=False)


@receiver(email_confirmed)
def approve_after_confirmation(sender, request, email_address, **kwargs):
    # Só depois de confirmar o e-mail: assim ninguém usa o e-mail de outra pessoa para ser aprovado
    from .services import approve_on_email_confirmation

    approve_on_email_confirmation(email_address.user, email_address.email)


@receiver(user_signed_up)
def notify_staff_of_signup(sender, request, user, **kwargs):
    from .tasks import notify_new_signup

    admin_url = request.build_absolute_uri(reverse("admin:accounts_user_change", args=[user.pk])) if request else ""
    transaction.on_commit(lambda: notify_new_signup.delay(user.pk, admin_url))
