from io import StringIO

import pytest
from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from django.core.management import call_command
from django.urls import reverse

from accounts.models import PreApprovedEmail, User
from moderation.models import ModerationAction

pytestmark = pytest.mark.django_db
PASSWORD = "senha-bem-forte-123"


def signup(client, email, username="autora"):
    client.post(reverse("account_signup"), {
        "email": email, "username": username, "password1": PASSWORD, "password2": PASSWORD, "confirm_adult": "on",
    })
    return User.objects.get(username=username)


def confirm(client, user):
    address = EmailAddress.objects.get(user=user)
    client.post(reverse("account_confirm_email", args=[EmailConfirmationHMAC(address).key]))


def test_pre_approved_email_is_approved_only_after_confirmation(client, admin_user, django_capture_on_commit_callbacks):
    PreApprovedEmail.objects.create(email="Amiga@Example.com", media_level=User.MediaLevel.IMAGES, created_by=admin_user)
    user = signup(client, "amiga@example.com")
    assert not user.is_approved  # cadastro sozinho não basta

    with django_capture_on_commit_callbacks(execute=True):
        confirm(client, user)
    user.refresh_from_db()
    entry = PreApprovedEmail.objects.get()
    assert user.is_approved and user.media_level == User.MediaLevel.IMAGES
    assert entry.used_by == user and entry.used_at
    assert ModerationAction.objects.filter(action="approve_account", object_id=user.pk, actor=admin_user).exists()


def test_other_emails_still_wait_for_approval(client):
    PreApprovedEmail.objects.create(email="amiga@example.com")
    user = signup(client, "outra@example.com")
    confirm(client, user)
    user.refresh_from_db()
    assert not user.is_approved


def test_pre_approval_is_used_only_once(client):
    PreApprovedEmail.objects.create(email="amiga@example.com")
    first = signup(client, "amiga@example.com")
    confirm(client, first)
    first.delete()  # a conta some; o e-mail liberado não vale de novo
    second = signup(client, "amiga@example.com", username="outra")
    confirm(client, second)
    second.refresh_from_db()
    assert not second.is_approved


def test_verify_email_command_applies_pre_approval(make_user):
    user = make_user("amiga", approved=False)
    PreApprovedEmail.objects.create(email=user.email.upper())
    out = StringIO()
    call_command("verify_email", "amiga", stdout=out)
    user.refresh_from_db()
    assert user.is_approved and "pré-aprovado" in out.getvalue()


def test_admin_adds_pre_approved_email(admin_client, admin_user):
    url = reverse("admin:accounts_preapprovedemail_add")
    admin_client.post(url, {"email": "Nova@Example.com", "media_level": 0, "note": "amiga da Carol"})
    entry = PreApprovedEmail.objects.get()
    assert entry.email == "nova@example.com" and entry.created_by == admin_user
    response = admin_client.post(url, {"email": "NOVA@example.com", "media_level": 0, "note": ""})
    assert response.status_code == 200 and PreApprovedEmail.objects.count() == 1  # duplicado recusado
