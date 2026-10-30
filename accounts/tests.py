import pytest
from django.core import mail
from django.urls import reverse

from accounts.models import Pseud, User
from moderation.models import ModerationAction

pytestmark = pytest.mark.django_db


def signup_data(**overrides):
    data = {
        "email": "nova@example.com",
        "username": "nova",
        "password1": "senha-bem-forte-123",
        "password2": "senha-bem-forte-123",
        "confirm_adult": "on",
    }
    data.update(overrides)
    return data


def test_signup_creates_pending_user_with_default_pseud(client):
    response = client.post(reverse("account_signup"), signup_data())
    assert response.status_code == 302
    user = User.objects.get(username="nova")
    assert user.is_approved is False
    assert user.adult_confirmed_at is not None
    assert user.media_level == User.MediaLevel.BASIC
    assert Pseud.objects.filter(user=user, is_default=True, name="nova").exists()
    # E-mail de verificação enviado
    assert len(mail.outbox) == 1


def test_signup_requires_adult_confirmation(client):
    data = signup_data()
    del data["confirm_adult"]
    response = client.post(reverse("account_signup"), data)
    assert response.status_code == 200
    assert not User.objects.filter(username="nova").exists()


def test_signup_closed(client, settings):
    settings.SIGNUP_OPEN = False
    client.post(reverse("account_signup"), signup_data())
    assert not User.objects.filter(username="nova").exists()


def test_pending_user_is_redirected(client, make_user):
    client.force_login(make_user(approved=False))
    response = client.get(reverse("home"))
    assert response.status_code == 302
    assert response.url == reverse("accounts:pending_approval")


def test_pending_user_can_open_account_pages(client, make_user):
    client.force_login(make_user(approved=False))
    assert client.get(reverse("accounts:pending_approval")).status_code == 200
    assert client.get(reverse("accounts:preferences")).status_code == 200


def test_approved_user_is_not_redirected(client, make_user):
    client.force_login(make_user())
    assert client.get(reverse("home")).status_code == 200


def test_superuser_is_approved_automatically(django_user_model):
    admin = django_user_model.objects.create_superuser("chefe", "chefe@example.com", "senha-bem-forte-123")
    assert admin.is_approved is True
    assert admin.approved_at is not None


def test_admin_approves_user_logs_and_emails(admin_client, admin_user, make_user, django_capture_on_commit_callbacks):
    pending = make_user(approved=False)
    with django_capture_on_commit_callbacks(execute=True):
        admin_client.post(
            reverse("admin:accounts_user_changelist"),
            {"action": "approve_users", "_selected_action": [pending.pk]},
        )
    pending.refresh_from_db()
    assert pending.is_approved is True
    assert pending.approved_by == admin_user
    assert ModerationAction.objects.filter(
        action=ModerationAction.Action.APPROVE_ACCOUNT, object_id=pending.pk, actor=admin_user
    ).exists()
    assert len(mail.outbox) == 1
    assert pending.email in mail.outbox[0].to


def test_approval_email_uses_user_language(admin_client, make_user, django_capture_on_commit_callbacks):
    pending = make_user(approved=False, language="en")
    with django_capture_on_commit_callbacks(execute=True):
        admin_client.post(
            reverse("admin:accounts_user_changelist"),
            {"action": "approve_users", "_selected_action": [pending.pk]},
        )
    assert "approved" in mail.outbox[0].subject


def test_admin_changes_media_level(admin_client, admin_user, make_user):
    author = make_user()
    admin_client.post(
        reverse("admin:accounts_user_changelist"),
        {"action": "set_media_images", "_selected_action": [author.pk]},
    )
    author.refresh_from_db()
    assert author.media_level == User.MediaLevel.IMAGES
    assert ModerationAction.objects.filter(action=ModerationAction.Action.CHANGE_MEDIA_LEVEL, object_id=author.pk).exists()


def test_reject_does_not_deactivate_self(admin_client, admin_user):
    admin_client.post(
        reverse("admin:accounts_user_changelist"),
        {"action": "reject_users", "_selected_action": [admin_user.pk]},
    )
    admin_user.refresh_from_db()
    assert admin_user.is_active is True


def test_preferences_save_language_and_cookie(client, make_user, settings):
    user = make_user()
    client.force_login(user)
    response = client.post(
        reverse("accounts:preferences"),
        {"language": "en", "hide_warnings": "on"},
    )
    assert response.status_code == 302
    user.refresh_from_db()
    assert user.language == "en"
    assert user.hide_warnings is True
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "en"
