from datetime import timedelta
from io import BytesIO

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import User
from tags.models import Tag
from works.models import Chapter, PublicationStatus, Work, WorkAuthor, WorkImage
from works.tasks import publish_scheduled

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media_in_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def author(make_user):
    return make_user("autora")


@pytest.fixture
def author_client(client, author):
    client.force_login(author)
    return client


def work_data(user, **overrides):
    data = {
        "title": "Minha obra",
        "pseuds": [user.default_pseud.pk],
        "rating": "teen",
        "warnings": ["none_apply"],
        "categories": ["gen"],
        "fandom_tags": "Fandom X",
        "relationship_tags": "",
        "character_tags": "Ana, Bia, ana",
        "freeform_tags": "Fluff",
        "language": "pt-br",
        "summary": "<p>Resumo</p>",
        "notes": "",
        "end_notes": "",
        "expected_chapters": "",
        "chapter-title": "",
        "chapter-summary": "",
        "chapter-notes": "",
        "chapter-content": "<p>Era uma vez três palavras</p>",
        "chapter-end_notes": "",
        "action": "publish",
        "scheduled_for": "",
    }
    data.update(overrides)
    return data


def create_work(client, user, **overrides):
    response = client.post(reverse("works:create"), work_data(user, **overrides))
    assert response.status_code == 302, response.context and response.context["form"].errors
    return Work.objects.latest("pk")


def png_upload(size=(3000, 2000), name="foto.png"):
    buffer = BytesIO()
    Image.new("RGB", size, "navy").save(buffer, "PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


# --- Criar e publicar ---


def test_create_and_publish_work(author_client, author):
    work = create_work(author_client, author)
    assert work.status == PublicationStatus.PUBLISHED
    assert work.published_at is not None
    chapter = work.chapters.get()
    assert chapter.status == PublicationStatus.PUBLISHED
    assert chapter.word_count == 5
    assert work.word_count == 5
    assert list(work.authors) == [author.default_pseud]
    names = sorted(work.tags.values_list("name", flat=True))
    assert names == ["Ana", "Bia", "Fandom X", "Fluff"]  # "ana" repetida foi ignorada
    assert Tag.objects.get(name="Fandom X").use_count == 1
    assert Tag.objects.get(name="Fandom X").type == Tag.Type.FANDOM


def test_content_is_sanitized(author_client, author):
    work = create_work(author_client, author, **{"chapter-content": "<p>oi <b>você</b></p><script>alert(1)</script>"})
    assert work.chapters.get().content == "<p>oi <b>você</b></p>"


def test_fandom_is_required(author_client, author):
    response = author_client.post(reverse("works:create"), work_data(author, fandom_tags=" , "))
    assert response.status_code == 200
    assert "fandom_tags" in response.context["form"].errors
    assert not Work.objects.exists()


def test_tag_type_conflict_is_an_error(author_client, author):
    Tag.objects.create(name="Fluff", type=Tag.Type.CHARACTER)
    response = author_client.post(reverse("works:create"), work_data(author))
    assert "freeform_tags" in response.context["form"].errors
    assert not Work.objects.exists()


def test_empty_chapter_is_an_error(author_client, author):
    response = author_client.post(reverse("works:create"), work_data(author, **{"chapter-content": "<p> </p>"}))
    assert "content" in response.context["chapter_form"].errors


def test_pending_user_cannot_create(client, make_user):
    pending = make_user("pendente", approved=False)
    client.force_login(pending)
    response = client.post(reverse("works:create"), work_data(pending))
    assert response.status_code == 302
    assert not Work.objects.exists()


# --- Rascunho, agendamento e visibilidade ---


def test_draft_is_only_visible_to_authors(client, author, make_user):
    client.force_login(author)
    work = create_work(client, author, action="draft")
    assert work.status == PublicationStatus.DRAFT
    url = reverse("works:detail", args=[work.pk])
    assert client.get(url).status_code == 200
    client.force_login(make_user("leitora"))
    assert client.get(url).status_code == 404
    client.logout()
    assert client.get(url).status_code == 404


def test_schedule_then_publish_task(author_client, author):
    when = (timezone.localtime() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    work = create_work(author_client, author, action="schedule", scheduled_for=when)
    assert work.status == PublicationStatus.SCHEDULED
    publish_scheduled()
    work.refresh_from_db()
    assert work.status == PublicationStatus.SCHEDULED  # ainda não chegou a hora

    Work.objects.filter(pk=work.pk).update(scheduled_for=timezone.now() - timedelta(minutes=1))
    Chapter.objects.filter(work=work).update(scheduled_for=timezone.now() - timedelta(minutes=1))
    publish_scheduled()
    work.refresh_from_db()
    assert work.status == PublicationStatus.PUBLISHED
    assert work.chapters.get().status == PublicationStatus.PUBLISHED


def test_schedule_in_the_past_is_an_error(author_client, author):
    when = (timezone.localtime() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    response = author_client.post(reverse("works:create"), work_data(author, action="schedule", scheduled_for=when))
    assert "scheduled_for" in response.context["publish_form"].errors


def test_restricted_work_requires_login(client, author):
    client.force_login(author)
    work = create_work(client, author, restricted="on")
    client.logout()
    response = client.get(reverse("works:detail", args=[work.pk]))
    assert response.status_code == 302
    assert reverse("account_login") in response.url


def test_adult_warning_for_visitors_only(client, author, make_user):
    client.force_login(author)
    work = create_work(client, author, rating="explicit")
    url = reverse("works:detail", args=[work.pk])
    client.logout()
    assert "Era uma vez" not in client.get(url).content.decode()
    assert "Era uma vez" in client.get(url + "?adulto=1").content.decode()
    assert "Era uma vez" in client.get(url).content.decode()  # lembrado na sessão
    client.force_login(make_user("adulta"))
    assert "Era uma vez" in client.get(url).content.decode()


def test_non_author_cannot_edit(client, author, make_user):
    client.force_login(author)
    work = create_work(client, author)
    client.force_login(make_user("intrusa"))
    assert client.get(reverse("works:edit", args=[work.pk])).status_code == 403
    assert client.post(reverse("works:delete", args=[work.pk])).status_code == 403


def test_edit_work_updates_tags_and_counts(author_client, author):
    work = create_work(author_client, author)
    data = work_data(author, freeform_tags="Angst", action="draft")
    response = author_client.post(reverse("works:edit", args=[work.pk]), data)
    assert response.status_code == 302
    work.refresh_from_db()
    assert work.status == PublicationStatus.PUBLISHED  # publicado continua publicado
    assert Tag.objects.get(name="Fluff").use_count == 0
    assert Tag.objects.get(name="Angst").use_count == 1


def test_delete_work(author_client, author):
    work = create_work(author_client, author)
    author_client.post(reverse("works:delete", args=[work.pk]))
    assert not Work.objects.filter(pk=work.pk).exists()
    assert Tag.objects.get(name="Fandom X").use_count == 0


# --- Capítulos ---


def chapter_data(content="<p>mais duas</p>", action="publish"):
    return {"title": "", "summary": "", "notes": "", "content": content, "end_notes": "", "action": action}


def test_add_chapters_and_word_count(client, author, make_user):
    client.force_login(author)
    work = create_work(client, author)
    client.post(reverse("works:chapter_create", args=[work.pk]), chapter_data())
    client.post(reverse("works:chapter_create", args=[work.pk]), chapter_data("<p>rascunho escondido aqui</p>", "draft"))
    work.refresh_from_db()
    assert list(work.chapters.values_list("position", "status")) == [(1, "published"), (2, "published"), (3, "draft")]
    assert work.word_count == 5 + 2  # rascunho não conta

    client.force_login(make_user("leitora"))
    assert client.get(reverse("works:chapter", args=[work.pk, 2])).status_code == 200
    assert client.get(reverse("works:chapter", args=[work.pk, 3])).status_code == 404


def test_delete_chapter_renumbers(author_client, author):
    work = create_work(author_client, author)
    for _ in range(2):
        author_client.post(reverse("works:chapter_create", args=[work.pk]), chapter_data())
    author_client.post(reverse("works:chapter_delete", args=[work.pk, 2]))
    assert list(work.chapters.values_list("position", flat=True)) == [1, 2]


def test_cannot_delete_only_chapter(author_client, author):
    work = create_work(author_client, author)
    author_client.post(reverse("works:chapter_delete", args=[work.pk, 1]))
    assert work.chapters.count() == 1


def test_full_work_view(author_client, author):
    work = create_work(author_client, author)
    author_client.post(reverse("works:chapter_create", args=[work.pk]), chapter_data("<p>segundo capítulo</p>"))
    content = author_client.get(reverse("works:full", args=[work.pk])).content.decode()
    assert "Era uma vez" in content and "segundo capítulo" in content


# --- Coautoria ---


def test_coauthor_invite_accept_and_edit(client, author, make_user, django_capture_on_commit_callbacks):
    client.force_login(author)
    work = create_work(client, author)
    guest = make_user("coautora")
    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("works:coauthor_invite", args=[work.pk]), {"username": "coautora"})
    authorship = WorkAuthor.objects.get(work=work, pseud__user=guest)
    assert authorship.status == WorkAuthor.Status.PENDING
    assert any(guest.email in message.to for message in mail.outbox)

    client.force_login(guest)
    assert client.get(reverse("works:edit", args=[work.pk])).status_code == 403
    client.post(reverse("works:respond_invitation", args=[authorship.pk]), {"decision": "accept"})
    assert client.get(reverse("works:edit", args=[work.pk])).status_code == 200
    assert len(list(work.authors)) == 2


def test_sole_author_cannot_leave(author_client, author):
    work = create_work(author_client, author)
    author_client.post(reverse("works:leave", args=[work.pk]))
    assert list(work.authors) == [author.default_pseud]


# --- Imagens ---


def test_basic_level_cannot_upload(author_client):
    response = author_client.post(reverse("works:image_upload"), {"image": png_upload()})
    assert response.status_code == 403
    assert not WorkImage.objects.exists()


def test_upload_converts_to_webp_and_resizes(client, make_user):
    user = make_user("ilustradora", media_level=User.MediaLevel.IMAGES)
    client.force_login(user)
    response = client.post(reverse("works:image_upload"), {"image": png_upload()})
    assert response.status_code == 200
    image = WorkImage.objects.get()
    assert image.file.name.endswith(".webp")
    assert image.width == 1600
    assert response.json()["url"].startswith("/media/imagens/")


def test_upload_rejects_non_images(client, make_user):
    client.force_login(make_user("ilustradora", media_level=User.MediaLevel.IMAGES))
    fake = SimpleUploadedFile("x.png", b"isso nao e imagem", content_type="image/png")
    assert client.post(reverse("works:image_upload"), {"image": fake}).status_code == 400


def test_upload_quota(client, make_user, settings):
    settings.IMAGE_QUOTA_MB = 0
    client.force_login(make_user("ilustradora", media_level=User.MediaLevel.IMAGES))
    assert client.post(reverse("works:image_upload"), {"image": png_upload()}).status_code == 400


def test_images_hidden_after_demotion(client, make_user):
    user = make_user("ilustradora", media_level=User.MediaLevel.IMAGES)
    client.force_login(user)
    url = client.post(reverse("works:image_upload"), {"image": png_upload()}).json()["url"]
    work = create_work(client, user, **{"chapter-content": f'<p>Veja</p><img src="{url}" alt="desenho">'})
    page = reverse("works:detail", args=[work.pk])
    assert url in client.get(page).content.decode()

    User.objects.filter(pk=user.pk).update(media_level=User.MediaLevel.BASIC)
    assert url not in client.get(page).content.decode()
    assert url in work.chapters.get().content  # oculta, mas não apagada


# --- Listas ---


def test_my_works_and_profile(client, author, make_user):
    client.force_login(author)
    published = create_work(client, author, title="Publicada")
    create_work(client, author, title="Rascunho secreto", action="draft")
    mine = client.get(reverse("works:my_works")).content.decode()
    assert "Publicada" in mine and "Rascunho secreto" in mine
    client.logout()
    profile = client.get(reverse("works:user_profile", args=[author.username])).content.decode()
    assert published.title in profile and "Rascunho secreto" not in profile
