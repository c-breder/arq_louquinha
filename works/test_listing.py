from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from interactions.models import Bookmark, Comment, Kudos
from tags.models import MetaTagging, Tag
from tags.wrangling import make_synonym
from works.listing import queue_refresh, refresh
from works.models import Chapter, PublicationStatus, Work, WorkAuthor, WorkListing

pytestmark = pytest.mark.django_db
T = Tag.Type


def make_tag(name, tag_type=T.FREEFORM, canonical=False, merger=None):
    return Tag.objects.create(name=name, type=tag_type, canonical=canonical, merger=merger)


def make_work(author, title, tags=(), words=100, rating="general", language="pt-br", complete=False,
              warnings=("none_apply",), status=PublicationStatus.PUBLISHED, days_ago=0, summary=""):
    when = timezone.now() - timedelta(days=days_ago)
    work = Work.objects.create(
        title=title, rating=rating, warnings=list(warnings), language=language, is_complete=complete,
        status=status, published_at=when if status == PublicationStatus.PUBLISHED else None,
        word_count=words, summary=summary,
    )
    WorkAuthor.objects.create(work=work, pseud=author.default_pseud, status=WorkAuthor.Status.ACCEPTED)
    Chapter.objects.create(work=work, position=1, content="<p>x</p>", status=status, word_count=words,
                           published_at=work.published_at)
    work.tags.set(tags)
    refresh([work.pk])
    return work


def titles(response):
    return [listing.title for listing in response.context["page"].object_list]


@pytest.fixture
def author(make_user):
    return make_user("Clarice")


@pytest.fixture
def library(author, make_user):
    au = make_tag("Universo Alternativo", canonical=True)
    cafe = make_tag("AU Cafeteria", canonical=True)
    MetaTagging.objects.create(meta=au, sub=cafe)
    coffee = make_tag("Coffee Shop AU", merger=cafe)
    angst = make_tag("Angst", canonical=True)
    fandom = make_tag("Fandom X", T.FANDOM, canonical=True)
    return {
        "tags": {"au": au, "cafe": cafe, "coffee": coffee, "angst": angst, "fandom": fandom},
        "cafe_work": make_work(author, "Café com Leite", [fandom, coffee], words=500, days_ago=1,
                               summary="<p>Uma história de <b>padaria</b></p>"),
        "angst_work": make_work(author, "Tristeza Infinita", [fandom, angst], words=50000, rating="mature",
                                language="en", complete=True, warnings=("violence",), days_ago=5),
        "draft": make_work(author, "Rascunho", [fandom], status=PublicationStatus.DRAFT),
    }


# --- Tabela de listagens ---


def test_listing_row_contents(library, author):
    work = library["cafe_work"]
    Kudos.objects.create(work=work, user=author)
    Bookmark.objects.create(work=work, pseud=author.default_pseud)
    Bookmark.objects.create(work=work, pseud=author.pseuds.create(name="Outro"), is_private=True)
    Comment.objects.create(chapter=work.chapters.first(), pseud=author.default_pseud, content="oi")
    refresh([work.pk])
    row = WorkListing.objects.get(work=work)
    t = library["tags"]
    assert row.visible
    assert set(row.filter_ids) == {t["fandom"].pk, t["cafe"].pk, t["au"].pk}  # sinônimo vira canônica + metatag
    assert (row.kudos_count, row.bookmark_count, row.comment_count) == (1, 1, 1)  # bookmark privado não conta
    assert row.card["authors"][0]["username"] == "Clarice"
    assert row.card["tags"]["freeform"] == [[t["coffee"].pk, "Coffee Shop AU"]]
    assert row.summary_text == "Uma história de padaria"


def test_drafts_are_not_listed(client, library):
    assert "Rascunho" not in titles(client.get(reverse("works:search")))


def test_wrangling_updates_listings(library, make_user):
    loose = make_tag("cafezinho")
    work = make_work(make_user("outra"), "Cafezinho", [loose])
    make_synonym(loose, library["tags"]["cafe"], make_user("wrangler"))
    row = WorkListing.objects.get(work=work)
    assert library["tags"]["au"].pk in row.filter_ids


def test_queue_refresh_runs_after_commit(settings, library, django_capture_on_commit_callbacks):
    settings.LISTING_REFRESH_SYNC = False
    work = library["cafe_work"]
    Work.objects.filter(pk=work.pk).update(title="Novo título")
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        queue_refresh([work.pk])
    assert len(callbacks) == 1
    assert WorkListing.objects.get(work=work).title == "Novo título"


def test_rebuild_command(library):
    from django.core.management import call_command

    WorkListing.objects.all().delete()
    call_command("rebuild_listings", stdout=open("/dev/null", "w"))
    assert WorkListing.objects.count() == 3


# --- Filtros ---


def search(client, **params):
    return titles(client.get(reverse("works:search"), params))


def test_include_by_metatag_reaches_synonym_of_subtag(client, library):
    assert search(client, incluir="Universo Alternativo") == ["Café com Leite"]
    assert search(client, incluir="coffee shop au") == ["Café com Leite"]


def test_include_multiple_tags_is_and(client, library):
    assert search(client, incluir="Fandom X, Angst") == ["Tristeza Infinita"]


def test_exclude_tags(client, library):
    assert search(client, excluir="Universo Alternativo") == ["Tristeza Infinita"]


def test_unknown_tag_shows_error(client, library):
    response = client.get(reverse("works:search"), {"incluir": "Não Existe"})
    assert "incluir" in response.context["form"].errors


def test_rating_warnings_language_complete(client, library):
    assert search(client, classificacao="mature") == ["Tristeza Infinita"]
    assert search(client, avisos="violence") == ["Tristeza Infinita"]
    assert search(client, idioma="en") == ["Tristeza Infinita"]
    assert search(client, completa="nao") == ["Café com Leite"]


def test_word_range_and_dates(client, library):
    assert search(client, palavras_min=1000) == ["Tristeza Infinita"]
    assert search(client, palavras_max=1000) == ["Café com Leite"]
    since = (timezone.localdate() - timedelta(days=2)).isoformat()
    assert search(client, desde=since) == ["Café com Leite"]


def test_sorting(client, library, author):
    Kudos.objects.create(work=library["angst_work"], user=author)
    refresh([library["angst_work"].pk])
    assert search(client) == ["Café com Leite", "Tristeza Infinita"]  # atualização mais recente
    assert search(client, ordenar="kudos")[0] == "Tristeza Infinita"
    assert search(client, ordenar="palavras")[0] == "Tristeza Infinita"
    assert search(client, ordenar="titulo") == ["Café com Leite", "Tristeza Infinita"]


def test_text_search_ignores_accents_and_matches_prefix(client, library):
    assert search(client, q="cafe") == ["Café com Leite"]
    assert search(client, q="padar") == ["Café com Leite"]  # resumo, por prefixo
    assert search(client, q="clarice") == ["Café com Leite", "Tristeza Infinita"]  # autora
    assert search(client, q="angst") == ["Tristeza Infinita"]  # tag
    assert search(client, q="clarice -cafe") == ["Tristeza Infinita"]


def test_restricted_and_hide_explicit(client, library, author, make_user):
    explicit = make_work(author, "Explícita", rating="explicit")
    Work.objects.filter(pk=explicit.pk).update(restricted=True)
    refresh([explicit.pk])
    assert "Explícita" not in search(client)  # visitante não vê "só para logados"
    reader = make_user("leitora")
    client.force_login(reader)
    assert "Explícita" in search(client)
    reader.hide_explicit = True
    reader.save()
    assert "Explícita" not in search(client)


def test_pagination_keeps_filters(client, author):
    for number in range(25):
        make_work(author, f"Obra {number:02d}", language="es")
    response = client.get(reverse("works:search"), {"idioma": "es"})
    assert response.context["page"].paginator.num_pages == 2
    assert "idioma=es" in response.content.decode()


def test_home_and_profile_use_listings(client, library, author):
    assert "Café com Leite" in client.get(reverse("home")).content.decode()
    assert "Café com Leite" in client.get(reverse("works:user_profile", args=[author.username])).content.decode()


def test_cached_card_changes_when_listing_refreshes(client, library):
    work = library["cafe_work"]
    assert "Café com Leite" in client.get(reverse("works:search")).content.decode()
    Work.objects.filter(pk=work.pk).update(title="Chá com Bolo")
    assert "Café com Leite" in client.get(reverse("works:search")).content.decode()  # ainda é o cache da linha antiga
    refresh([work.pk])
    content = client.get(reverse("works:search")).content.decode()
    assert "Chá com Bolo" in content and "Café com Leite" not in content


def test_cached_card_respects_language(client, library):
    assert "Palavras" in client.get(reverse("works:search")).content.decode()
    client.cookies["django_language"] = "en"
    assert "Words" in client.get(reverse("works:search")).content.decode()


# --- Limite de pedidos ---


def test_rate_limit(client, settings):
    settings.RATE_LIMIT_SEARCH = 3
    codes = [client.get(reverse("works:search")).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert client.get(reverse("home")).status_code == 200  # outras páginas seguem no limite geral
