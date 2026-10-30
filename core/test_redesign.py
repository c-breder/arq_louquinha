from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from interactions.models import Kudos
from tags.models import Tag
from works.listing import refresh
from works.models import Chapter, PublicationStatus, Work, WorkAuthor

pytestmark = pytest.mark.django_db


def make_work(author, title, kudos=0, days_ago=1, complete=False, restricted=False, tags=()):
    when = timezone.now() - timedelta(days=days_ago)
    work = Work.objects.create(
        title=title, rating="general", warnings=["none_apply"], status=PublicationStatus.PUBLISHED,
        published_at=when, is_complete=complete, restricted=restricted,
    )
    WorkAuthor.objects.create(work=work, pseud=author.default_pseud, status=WorkAuthor.Status.ACCEPTED)
    Chapter.objects.create(work=work, position=1, content="<p>x</p>", status=PublicationStatus.PUBLISHED,
                           published_at=when)
    work.tags.set(tags)
    for number in range(kudos):
        Kudos.objects.create(work=work, guest_key=f"k{work.pk}-{number}")
    refresh([work.pk])
    return work


def test_brand_layout_and_quote(client, settings):
    content = client.get(reverse("home")).content.decode()
    assert settings.SITE_NAME == "Arquivo Louquinha"
    assert content.count("Arquivo Louquinha") >= 2  # cabeçalho e rodapé
    assert "Um arquivo de histórias." in content
    assert "Nenhum gesto humano pode abolir o acaso" in content and "Zenilda" in content
    assert "Algumas histórias não cabem em um só lugar" not in content
    assert "Feito por alguém que também ama histórias." in content
    for name in ("about", "terms", "contact"):
        assert reverse(name) in content


def test_home_sections_use_real_data(client, make_user):
    author = make_user("autora")
    fandom = Tag.objects.create(name="Três Graças", type=Tag.Type.FANDOM, canonical=True)
    fluff = Tag.objects.create(name="Fluff", type=Tag.Type.FREEFORM)
    popular = make_work(author, "Muito Querida", kudos=5, complete=True, tags=[fandom, fluff])
    make_work(author, "Menos Querida", kudos=1)
    content = client.get(reverse("home")).content.decode()
    assert content.index("Muito Querida") < content.index("Menos Querida")  # destaque por kudos
    assert "Concluída" in content and "Em andamento" in content
    assert "Três Graças" in content and "Fluff" in content
    assert f'href="/obras/{popular.pk}/"' in content
    assert "<img" not in content.split("Obras em destaque")[1].split("Navegue por")[0]  # sem capas
    assert "Últimas atualizações" in content and f"/obras/{popular.pk}/capitulos/1/" in content


def test_home_hides_restricted_from_visitors(client, make_user):
    make_work(make_user("autora"), "Só Logados", restricted=True)
    assert "Só Logados" not in client.get(reverse("home")).content.decode()


def test_navigation_marks_current_page(client):
    content = client.get(reverse("tags:fandoms")).content.decode()
    assert 'href="/fandoms/" class="is-active" aria-current="page"' in content


def test_institutional_pages(client, admin_client):
    for name, title in (("about", "Sobre"), ("terms", "Termos de Uso"), ("contact", "Contato")):
        response = client.get(reverse(name))
        assert response.status_code == 200 and title in response.content.decode()
    assert "Arquivo Louquinha é uma plataforma" in client.get(reverse("about")).content.decode()
    assert "Editar esta página" in admin_client.get(reverse("about")).content.decode()


def test_user_menu_keeps_all_links(client, make_user):
    client.force_login(make_user("autora"))
    content = client.get(reverse("home")).content.decode()
    for url in ("/obras/nova/", "/obras/importar/", "/minhas-obras/", "/mensagens/", "/conta/preferencias/", "/conta/logout/"):
        assert url in content, url
