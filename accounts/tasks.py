from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import translation
from django.utils.translation import gettext as _


@shared_task
def send_approval_email(user_id):
    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        return
    # E-mail no idioma escolhido pela pessoa
    with translation.override(user.language):
        subject = _("Sua conta foi aprovada")
        body = _(
            "Olá, %(username)s!\n\nSua conta no %(site)s foi aprovada. Você já pode entrar e usar o site."
        ) % {"username": user.username, "site": settings.SITE_NAME}
    send_mail(f"[{settings.SITE_NAME}] {subject}", body, None, [user.email])
