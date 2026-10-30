from datetime import timedelta

import pytest
from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from accounts.models import PreApprovedEmail, User
from core.models import SiteSettings
from moderation.models import ModerationAction

pytestmark = pytest.mark.django_db
PASSWORD = "senha-bem-forte-123"


def signup(client, email="nova@example.com", username="nova"):
    client.post(reverse("account_signup"), {
        "email": email, "username": username, "password1": PASSWORD, "password2": PASSWORD, "confirm_adult": "on",
    })
    return User.objects.get(username=username)


def confirm(client, user):
    address = EmailAddress.objects.get(user=user)
    client.post(reverse("account_confirm_email", args=[EmailConfirmationHMAC(address).key]))
    user.refresh_from_db()


def open_window(hours=2):
    settings = SiteSettings.current()
    settings.open_signup_until = timezone.now() + timedelta(hours=hours)
    settings.save()


# --- Janela de cadastro aberto ---


def test_open_window_approves_after_confirmation(client):
    open_window()
    user = signup(client)
    assert not user.is_approved
    confirm(client, user)
    assert user.is_approved and user.media_level == User.MediaLevel.BASIC
    assert ModerationAction.objects.filter(
        action="approve_account", object_id=user.pk, note="janela de cadastro aberto"
    ).exists()


def test_closed_or_expired_window_keeps_manual_approval(client):
    user = signup(client)
    confirm(client, user)
    assert not user.is_approved
    open_window(hours=-1)  # já passou
    late = signup(client, "tarde@example.com", "tarde")
    confirm(client, late)
    assert not late.is_approved


def test_signup_page_shows_open_window(client):
    assert "Cadastros abertos até" not in client.get(reverse("account_signup")).content.decode()
    open_window()
    assert "Cadastros abertos até" in client.get(reverse("account_signup")).content.decode()
    assert "Cadastros abertos até" not in client.get(reverse("home")).content.decode()


def test_pre_approval_wins_over_window(client, admin_user):
    open_window()
    PreApprovedEmail.objects.create(email="amiga@example.com", media_level=User.MediaLevel.IMAGES, created_by=admin_user)
    user = signup(client, "amiga@example.com", "amiga")
    confirm(client, user)
    assert user.media_level == User.MediaLevel.IMAGES
    assert ModerationAction.objects.get(object_id=user.pk, action="approve_account").actor == admin_user


# --- Aviso de nova conta ---


def test_staff_is_emailed_on_each_signup(client, django_capture_on_commit_callbacks):
    settings = SiteSettings.current()
    settings.notify_emails = "dona@example.com\noutra@example.com"
    settings.save()
    with django_capture_on_commit_callbacks(execute=True):
        signup(client)
    notices = [message for message in mail.outbox if "Nova conta" in message.subject]
    assert len(notices) == 1
    assert notices[0].to == ["dona@example.com", "outra@example.com"]
    assert "nova@example.com" in notices[0].body and "aguardando a sua aprovação" in notices[0].body
    assert "/admin/accounts/user/" in notices[0].body


def test_no_notice_without_recipients(client, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        signup(client)
    assert not [message for message in mail.outbox if "Nova conta" in message.subject]


def test_admin_settings_page(admin_client):
    response = admin_client.get(reverse("admin:core_sitesettings_changelist"), follow=True)
    assert response.status_code == 200 and "notify_emails" in response.content.decode()
