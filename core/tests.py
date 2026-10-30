from io import StringIO

import pytest
from django.contrib import admin
from django.core.management import call_command
from django.urls import reverse

from accounts.models import User
from tags.models import Tag
from works.models import Chapter, Work

pytestmark = pytest.mark.django_db


def test_healthz(client):
    response = client.get(reverse("healthz"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_status_is_staff_only(client, admin_client):
    assert client.get(reverse("status")).status_code == 404
    data = admin_client.get(reverse("status")).json()
    assert data["database_mb"] > 0
    assert "works" in data["counts"]


def test_status_command():
    out = StringIO()
    call_command("status", stdout=out)
    assert "Tamanho" in out.getvalue()


# --- Idioma ---


def test_portuguese_is_default_even_if_browser_asks_english(client):
    response = client.get(reverse("home"), HTTP_ACCEPT_LANGUAGE="en-US,en;q=0.9")
    assert response["Content-Language"] == "pt-br"
    assert "Obras em destaque" in response.content.decode()


def test_cookie_switches_to_english(client, settings):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
    response = client.get(reverse("home"))
    assert response["Content-Language"] == "en"
    assert "Featured works" in response.content.decode()


def test_unknown_language_falls_back_to_portuguese(client, settings):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "xx"
    assert client.get(reverse("home"))["Content-Language"] == "pt-br"


def test_user_preference_wins_over_cookie(client, make_user, settings):
    client.force_login(make_user(language="en"))
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "pt-br"
    assert client.get(reverse("home"))["Content-Language"] == "en"


def test_set_language_view_saves_on_account(client, make_user, settings):
    user = make_user()
    client.force_login(user)
    response = client.post(reverse("set_language"), {"language": "en", "next": "/"})
    assert response.status_code == 302
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "en"
    user.refresh_from_db()
    assert user.language == "en"


def test_set_language_rejects_external_redirect(client):
    response = client.post(reverse("set_language"), {"language": "en", "next": "https://malicioso.example/"})
    assert response.url == "/"


# --- Admin ---


def test_admin_pages_load(admin_client, admin_user, rf):
    # Abre a lista e o formulário de cada modelo registrado
    request = rf.get("/")
    request.user = admin_user
    for model, model_admin in admin.site._registry.items():
        info = (model._meta.app_label, model._meta.model_name)
        assert admin_client.get(reverse("admin:%s_%s_changelist" % info)).status_code == 200, info
        if model_admin.has_add_permission(request):
            assert admin_client.get(reverse("admin:%s_%s_add" % info)).status_code == 200, info


# --- Seed ---


def test_seed_creates_consistent_data():
    call_command("seed", users=6, fandoms=2, freeforms=10, works=15, force=True, stdout=StringIO())
    assert User.objects.filter(email__endswith="@seed.invalid").count() == 6
    assert Work.objects.count() == 15
    work = Work.objects.filter(chapters__isnull=False).first()
    assert work.word_count == sum(Chapter.objects.filter(work=work).values_list("word_count", flat=True))
    assert Tag.objects.filter(merger__isnull=False).exists()
    used = Tag.objects.filter(use_count__gt=0).first()
    assert used.use_count == used.works.count()


def test_seed_clear_removes_previous_run():
    call_command("seed", users=4, fandoms=1, freeforms=5, works=5, force=True, stdout=StringIO())
    call_command("seed", users=3, fandoms=1, freeforms=5, works=4, clear=True, force=True, stdout=StringIO())
    assert User.objects.filter(email__endswith="@seed.invalid").count() == 3
    assert Work.objects.count() == 4


def test_seed_refuses_without_debug():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("seed", works=1)
