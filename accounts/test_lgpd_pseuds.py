import json
from io import BytesIO

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from accounts.models import Pseud, User
from works.models import Chapter, PublicationStatus, Work, WorkAuthor

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_in_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def png(size=(500, 300)):
    buffer = BytesIO()
    Image.new("RGB", size, "white").save(buffer, "PNG")
    return SimpleUploadedFile("avatar.png", buffer.getvalue(), content_type="image/png")


def make_work(*pseuds, title="Obra"):
    work = Work.objects.create(
        title=title,
        rating=Work.Rating.GENERAL,
        warnings=[Work.Warning.NONE_APPLY],
        status=PublicationStatus.PUBLISHED,
    )
    for pseud in pseuds:
        WorkAuthor.objects.create(work=work, pseud=pseud, status=WorkAuthor.Status.ACCEPTED)
    Chapter.objects.create(work=work, position=1, content="<p>texto</p>", status=PublicationStatus.PUBLISHED)
    return work


# --- Pseudônimos ---


def test_create_pseud_with_square_webp_avatar(client, make_user):
    user = make_user()
    client.force_login(user)
    response = client.post(
        reverse("accounts:pseud_create"), {"name": "Outro Nome", "description": "", "avatar_upload": png()}
    )
    assert response.status_code == 302
    pseud = user.pseuds.get(name="Outro Nome")
    assert pseud.avatar.name.endswith(".webp")
    with Image.open(pseud.avatar.path) as image:
        assert image.size == (settings.AVATAR_SIZE, settings.AVATAR_SIZE)


def test_pseud_name_unique_per_user(client, make_user):
    user = make_user("ana")
    client.force_login(user)
    response = client.post(reverse("accounts:pseud_create"), {"name": "ANA", "description": ""})
    assert response.status_code == 200
    assert user.pseuds.count() == 1


def test_replacing_avatar_deletes_old_file(client, make_user):
    user = make_user()
    client.force_login(user)
    pseud = user.default_pseud
    url = reverse("accounts:pseud_edit", args=[pseud.pk])
    client.post(url, {"name": pseud.name, "description": "", "avatar_upload": png()})
    pseud.refresh_from_db()
    old_path = pseud.avatar.path
    client.post(url, {"name": pseud.name, "description": "", "avatar_upload": png((100, 100))})
    pseud.refresh_from_db()
    assert pseud.avatar.path != old_path
    import os

    assert not os.path.exists(old_path)


def test_delete_pseud_moves_works_to_default(client, make_user):
    user = make_user()
    extra = Pseud.objects.create(user=user, name="Secundário")
    work = make_work(extra)
    client.force_login(user)
    client.post(reverse("accounts:pseud_delete", args=[extra.pk]))
    assert not Pseud.objects.filter(pk=extra.pk).exists()
    assert list(work.authors) == [user.default_pseud]


def test_default_pseud_cannot_be_deleted(client, make_user):
    user = make_user()
    client.force_login(user)
    client.post(reverse("accounts:pseud_delete", args=[user.default_pseud.pk]))
    assert user.pseuds.count() == 1


def test_make_default(client, make_user):
    user = make_user()
    extra = Pseud.objects.create(user=user, name="Novo")
    client.force_login(user)
    client.post(reverse("accounts:pseud_make_default", args=[extra.pk]))
    assert user.default_pseud == extra
    assert user.pseuds.filter(is_default=True).count() == 1


# --- LGPD ---


def test_export_data(client, make_user):
    user = make_user()
    make_work(user.default_pseud, title="Minha história")
    client.force_login(user)
    response = client.get(reverse("accounts:export_data"))
    assert response["Content-Disposition"].startswith("attachment")
    data = json.loads(response.content)
    assert data["account"]["username"] == user.username
    assert data["works"][0]["title"] == "Minha história"
    assert data["works"][0]["chapters"][0]["content"] == "<p>texto</p>"


def delete_data(user, works="orphan"):
    return {"works": works, "confirm_username": user.username, "password": "senha-bem-forte-123"}


def test_delete_account_orphans_works(client, make_user):
    user = make_user()
    work = make_work(user.default_pseud)
    client.force_login(user)
    response = client.post(reverse("accounts:delete_account"), delete_data(user))
    assert response.status_code == 302
    assert not User.objects.filter(pk=user.pk).exists()
    work.refresh_from_db()
    assert [pseud.user.username for pseud in work.authors] == [settings.ORPHAN_USERNAME]


def test_delete_account_with_works(client, make_user):
    user = make_user()
    partner = make_user("parceira")
    solo = make_work(user.default_pseud, title="Solo")
    shared = make_work(user.default_pseud, partner.default_pseud, title="Dupla")
    client.force_login(user)
    client.post(reverse("accounts:delete_account"), delete_data(user, works="delete"))
    assert not Work.objects.filter(pk=solo.pk).exists()
    assert list(shared.authors) == [partner.default_pseud]


def test_delete_account_requires_confirmation(client, make_user):
    user = make_user()
    client.force_login(user)
    data = delete_data(user)
    data["confirm_username"] = "outra"
    client.post(reverse("accounts:delete_account"), data)
    data = delete_data(user)
    data["password"] = "errada"
    client.post(reverse("accounts:delete_account"), data)
    assert User.objects.filter(pk=user.pk).exists()
