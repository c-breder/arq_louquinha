from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone, translation
from django.utils.translation import gettext as _


@shared_task
def notify_new_signup(user_id, admin_url=""):
    """Avisa a equipe (lista em Configurações do site) a cada conta criada."""
    from core.models import SiteSettings

    from .models import PreApprovedEmail

    site_settings = SiteSettings.current()
    recipients = site_settings.notify_list
    user = get_user_model().objects.filter(pk=user_id).first()
    if not recipients or user is None:
        return
    if PreApprovedEmail.objects.filter(email=user.email.lower(), used_at__isnull=True).exists():
        situation = "e-mail pré-aprovado: será aprovada ao confirmar o e-mail"
    elif site_settings.signup_window_open:
        situation = "janela de cadastro aberta: será aprovada ao confirmar o e-mail"
    else:
        situation = "aguardando a sua aprovação no admin"
    body = (
        f"Nova conta criada no {settings.SITE_NAME}.\n\n"
        f"Usuário: {user.username}\n"
        f"E-mail: {user.email}\n"
        f"Criada em: {timezone.localtime(user.date_joined):%d/%m/%Y %H:%M}\n"
        f"Situação: {situation}\n"
    )
    if admin_url:
        body += f"\nVer no admin: {admin_url}\n"
    send_mail(f"[{settings.SITE_NAME}] Nova conta: {user.username}", body, None, recipients)


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
