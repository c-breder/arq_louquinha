import json

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.urls import reverse

from accounts.services import export_user_data
from challenges.models import Collection, CollectionItem, Prompt
from interactions.models import Bookmark, Comment, Kudos
from interactions.tasks import flush_counters
from messaging.models import Conversation, Message
from moderation.models import ModerationAction, Report
from works.listing import refresh
from works.models import Chapter, PublicationStatus, Series, SeriesWork, Work, WorkAuthor, WorkListing

pytestmark = pytest.mark.django_db


def make_work(author, title="Obra", **extra):
    work = Work.objects.create(
        title=title, rating=Work.Rating.GENERAL, warnings=[Work.Warning.NONE_APPLY],
        status=PublicationStatus.PUBLISHED, **extra,
    )
    WorkAuthor.objects.create(work=work, pseud=author.default_pseud, status=WorkAuthor.Status.ACCEPTED)
    Chapter.objects.create(work=work, position=1, content="<p>texto</p>", status=PublicationStatus.PUBLISHED)
    refresh([work.pk])
    return work


@pytest.fixture
def author(make_user):
    return make_user("autora")


@pytest.fixture
def work(author):
    return make_work(author)


# --- Kudos e acessos (Redis + gravação em lote) ---


def test_kudos_from_user_and_guest_are_batched(client, work, make_user):
    reader = make_user("leitora")
    client.force_login(reader)
    client.post(reverse("interactions:kudos", args=[work.pk]))
    client.post(reverse("interactions:kudos", args=[work.pk]))  # repetido
    client.logout()
    client.post(reverse("interactions:kudos", args=[work.pk]))  # visitante
    client.post(reverse("interactions:kudos", args=[work.pk]))  # mesma sessão
    assert Kudos.objects.count() == 0  # ainda no Redis
    page = client.get(reverse("works:detail", args=[work.pk])).content.decode()
    assert "Kudos: 2" in page  # já conta os pendentes

    flush_counters()
    assert Kudos.objects.filter(work=work, user=reader).count() == 1
    assert Kudos.objects.filter(work=work, user__isnull=True).count() == 1
    assert WorkListing.objects.get(work=work).kudos_count == 2
    assert "Kudos: 2" in client.get(reverse("works:detail", args=[work.pk])).content.decode()


def test_author_cannot_kudos_own_work(client, work, author):
    client.force_login(author)
    client.post(reverse("interactions:kudos", args=[work.pk]))
    flush_counters()
    assert not Kudos.objects.exists()


def test_already_flushed_kudos_is_not_repeated(client, work, make_user):
    client.force_login(make_user("leitora"))
    client.post(reverse("interactions:kudos", args=[work.pk]))
    flush_counters()
    client.post(reverse("interactions:kudos", args=[work.pk]))
    flush_counters()
    assert Kudos.objects.count() == 1


def test_hits_once_per_visitor_and_not_for_author_or_bots(client, work, author, make_user):
    url = reverse("works:detail", args=[work.pk])
    client.get(url)
    client.get(url)  # mesmo visitante (IP)
    client.get(url, HTTP_USER_AGENT="Googlebot/2.1")
    client.force_login(author)
    client.get(url)
    client.force_login(make_user("leitora"))
    client.get(url)
    flush_counters()
    work.refresh_from_db()
    assert work.hit_count == 2
    assert WorkListing.objects.get(work=work).hit_count == 2


# --- Comentários ---


def comment(client, work, text, parent=None, position=1):
    data = {"content": text}
    if parent:
        data["parent"] = parent.pk
    return client.post(reverse("interactions:comment", args=[work.pk, position]), data)


def test_threaded_comments_and_email(client, work, make_user, django_capture_on_commit_callbacks):
    reader = make_user("leitora")
    client.force_login(reader)
    with django_capture_on_commit_callbacks(execute=True):
        comment(client, work, "Amei! <script>x</script>")
    first = Comment.objects.get()
    assert "script" not in first.content
    assert any("autora@example.com" in message.to for message in mail.outbox)

    other = make_user("outra")
    client.force_login(other)
    with django_capture_on_commit_callbacks(execute=True):
        comment(client, work, "Eu também", parent=first)
    reply = Comment.objects.get(parent=first)
    assert any("leitora@example.com" in message.to for message in mail.outbox)  # avisa quem recebeu resposta
    page = client.get(reverse("works:detail", args=[work.pk])).content.decode()
    assert f'id="comentario-{reply.pk}" class="comment depth-1"' in page
    assert WorkListing.objects.get(work=work).comment_count == 2


def test_comment_permissions(client, work, author, make_user):
    reader = make_user("leitora")
    client.force_login(reader)
    comment(client, work, "Oi")
    item = Comment.objects.get()
    client.force_login(make_user("intrusa"))
    assert client.post(reverse("interactions:comment_delete", args=[item.pk])).status_code == 403
    assert client.get(reverse("interactions:comment_edit", args=[item.pk])).status_code == 403
    client.force_login(author)  # autora da obra pode apagar
    client.post(reverse("interactions:comment_delete", args=[item.pk]))
    assert not Comment.objects.exists()


def test_deleting_comment_with_replies_keeps_thread(client, work, make_user):
    reader = make_user("leitora")
    client.force_login(reader)
    comment(client, work, "Primeiro")
    first = Comment.objects.get()
    comment(client, work, "Resposta", parent=first)
    client.post(reverse("interactions:comment_delete", args=[first.pk]))
    first.refresh_from_db()
    assert first.deleted and first.content == ""
    assert "(comentário apagado)" in client.get(reverse("works:detail", args=[work.pk])).content.decode()


def test_visitors_and_pending_users_cannot_comment(client, work, make_user):
    comment(client, work, "anônimo")
    client.force_login(make_user("pendente", approved=False))
    comment(client, work, "pendente")
    assert not Comment.objects.exists()


def test_comment_rate_limit(client, work, make_user, settings):
    settings.COMMENTS_PER_HOUR = 2
    client.force_login(make_user("leitora"))
    for number in range(4):
        comment(client, work, f"c{number}")
    assert Comment.objects.count() == 2


# --- Bookmarks ---


def test_bookmarks(client, work, make_user):
    reader = make_user("leitora")
    client.force_login(reader)
    client.post(reverse("interactions:bookmark", args=[work.pk]), {
        "pseud": reader.default_pseud.pk, "notes": "<p>Favorita</p>", "tag_names": "Para reler, Conforto",
    })
    bookmark = Bookmark.objects.get()
    assert sorted(bookmark.tags.values_list("name", flat=True)) == ["Conforto", "Para reler"]
    assert WorkListing.objects.get(work=work).bookmark_count == 1
    assert "Favorita" in client.get(reverse("interactions:user_bookmarks", args=["leitora"])).content.decode()

    client.post(reverse("interactions:bookmark", args=[work.pk]), {
        "pseud": reader.default_pseud.pk, "notes": "Secreta", "tag_names": "", "is_private": "on",
    })
    assert Bookmark.objects.count() == 1  # editou o mesmo
    client.logout()
    assert "Secreta" not in client.get(reverse("interactions:user_bookmarks", args=["leitora"])).content.decode()
    assert WorkListing.objects.get(work=work).bookmark_count == 0  # privado não conta


# --- Séries ---


def test_series_flow(client, author):
    first, second, third = (make_work(author, title) for title in ("Um", "Dois", "Três"))
    client.force_login(author)
    client.post(reverse("works:add_to_series", args=[first.pk]), {"new_title": "Trilogia"})
    series = Series.objects.get(title="Trilogia")
    for work in (second, third):
        client.post(reverse("works:add_to_series", args=[work.pk]), {"series": series.pk})
    assert list(series.entries.order_by("position").values_list("work__title", flat=True)) == ["Um", "Dois", "Três"]

    page = client.get(reverse("works:detail", args=[second.pk])).content.decode()
    assert "Parte 2 de" in page and f'href="/obras/{first.pk}/"' in page and f'href="/obras/{third.pk}/"' in page

    entry = series.entries.get(work=third)
    client.post(reverse("works:series_move", args=[series.pk, entry.pk, "subir"]))
    assert list(series.entries.order_by("position").values_list("work__title", flat=True)) == ["Um", "Três", "Dois"]

    client.post(reverse("works:remove_from_series", args=[first.pk, series.pk]))
    assert list(series.entries.order_by("position").values_list("position", flat=True)) == [1, 2]
    assert "Trilogia" in client.get(reverse("works:series", args=[series.pk])).content.decode()


def test_series_edit_permission(client, author, make_user):
    work = make_work(author)
    series = Series.objects.create(title="S")
    series.pseuds.add(author.default_pseud)
    SeriesWork.objects.create(series=series, work=work, position=1)
    client.force_login(make_user("intrusa"))
    assert client.get(reverse("works:series_edit", args=[series.pk])).status_code == 403


# --- Coleções e desafios ---


def test_moderated_collection(client, author, make_user):
    owner = make_user("curadora")
    client.force_login(owner)
    client.post(reverse("challenges:create"), {
        "title": "Desafio de Natal", "slug": "natal", "kind": "prompt_meme", "description": "",
        "is_open": "on", "is_moderated": "on", "closes_at": "",
    })
    collection = Collection.objects.get(slug="natal")
    client.post(reverse("challenges:add_prompt", args=["natal"]), {"text": "Neve e chocolate quente"})
    prompt = Prompt.objects.get()

    work = make_work(author)
    client.force_login(author)
    client.post(reverse("challenges:add_work", args=[work.pk]), {"collection": "natal", "prompt": prompt.pk})
    item = CollectionItem.objects.get()
    assert item.status == CollectionItem.Status.PENDING and item.prompt == prompt
    assert "Obra" not in titles_on(client, "natal")

    client.force_login(owner)
    client.post(reverse("challenges:manage", args=["natal"]), {"item": item.pk, "decision": "approved"})
    assert "1 resposta" in client.get(reverse("challenges:detail", args=["natal"])).content.decode()
    assert "Obra" in titles_on(client, "natal")
    assert collection.title in client.get(reverse("works:detail", args=[work.pk])).content.decode()


def titles_on(client, slug):
    page = client.get(reverse("challenges:detail", args=[slug])).context["page"]
    return [listing.title for listing in page.object_list]


def test_closed_collection_refuses_works(client, author, make_user):
    Collection.objects.create(slug="fechada", title="Fechada", owner=make_user("dona"), is_open=False)
    work = make_work(author)
    client.force_login(author)
    client.post(reverse("challenges:add_work", args=[work.pk]), {"collection": "fechada"})
    assert not CollectionItem.objects.exists()


def test_only_manager_can_moderate(client, author, make_user):
    collection = Collection.objects.create(slug="x", title="X", owner=make_user("dona"))
    client.force_login(author)
    assert client.get(reverse("challenges:manage", args=[collection.slug])).status_code == 403


# --- Mensagens privadas ---


def test_messages_flow(client, make_user):
    sender, recipient = make_user("ana"), make_user("bia")
    client.force_login(sender)
    response = client.post(reverse("messaging:new"), {"to": "BIA", "body": "Oi, Bia!"})
    conversation = Conversation.objects.get()
    assert response.url == reverse("messaging:thread", args=[conversation.pk])
    assert Conversation.unread_for(recipient).count() == 1
    assert Conversation.unread_for(sender).count() == 0

    client.force_login(recipient)
    page = client.get(reverse("messaging:thread", args=[conversation.pk])).content.decode()
    assert "Oi, Bia!" in page
    assert Conversation.unread_for(recipient).count() == 0
    client.post(reverse("messaging:thread", args=[conversation.pk]), {"body": "Oi, Ana!"})
    assert Conversation.unread_for(sender).count() == 1
    assert Message.objects.count() == 2

    client.force_login(make_user("curiosa"))
    assert client.get(reverse("messaging:thread", args=[conversation.pk])).status_code == 403


def test_messages_respect_preference_and_rate_limit(client, make_user, settings):
    sender = make_user("ana")
    make_user("reservada", allow_messages=False)
    make_user("bia")
    client.force_login(sender)
    client.post(reverse("messaging:new"), {"to": "reservada", "body": "oi"})
    client.post(reverse("messaging:new"), {"to": "ana", "body": "eu mesma"})
    assert not Message.objects.exists()
    settings.MESSAGES_PER_HOUR = 2
    for number in range(4):
        client.post(reverse("messaging:new"), {"to": "bia", "body": f"m{number}"})
    assert Message.objects.count() == 2


def test_export_includes_messages(make_user):
    sender, recipient = make_user("ana"), make_user("bia")
    conversation = Conversation.between(sender, recipient)
    Message.objects.create(conversation=conversation, sender=sender, body="segredo")
    data = json.loads(json.dumps(export_user_data(sender), default=str))
    assert data["messages_sent"][0] == {"to": "bia", "body": "segredo", "created_at": data["messages_sent"][0]["created_at"]}


# --- Denúncias e moderação ---


def test_report_and_hide_from_admin(client, admin_client, work, make_user):
    reporter = make_user("leitora")
    client.force_login(reporter)
    url = reverse("moderation:report", args=["work", work.pk])
    client.post(url, {"reason": "plagiarism", "details": "Copiado de outro site"})
    client.post(url, {"reason": "plagiarism", "details": "de novo"})  # não duplica
    report = Report.objects.get()
    assert report.content_type == ContentType.objects.get_for_model(Work)

    admin_client.post(reverse("admin:moderation_report_changelist"), {"action": "hide_targets", "_selected_action": [report.pk]})
    work.refresh_from_db()
    report.refresh_from_db()
    assert work.hidden_by_moderator
    assert report.status == Report.Status.RESOLVED
    assert ModerationAction.objects.filter(action="hide", report=report).exists()
    assert not WorkListing.objects.get(work=work).visible
    client.logout()
    assert client.get(reverse("works:detail", args=[work.pk])).status_code == 404


def test_report_user_and_suspend(client, admin_client, make_user):
    target = make_user("spammer")
    client.force_login(make_user("leitora"))
    client.post(reverse("moderation:report", args=["user", target.pk]), {"reason": "spam", "details": ""})
    report = Report.objects.get()
    admin_client.post(reverse("admin:moderation_report_changelist"), {"action": "suspend_owners", "_selected_action": [report.pk]})
    target.refresh_from_db()
    assert not target.is_active


def test_cannot_report_message_of_other_conversation(client, make_user):
    ana, bia = make_user("ana"), make_user("bia")
    message = Message.objects.create(conversation=Conversation.between(ana, bia), sender=ana, body="x")
    client.force_login(make_user("curiosa"))
    assert client.get(reverse("moderation:report", args=["message", message.pk])).status_code == 404
    client.force_login(bia)
    assert client.get(reverse("moderation:report", args=["message", message.pk])).status_code == 200
