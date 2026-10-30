import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from accounts.models import User
from moderation.models import ModerationAction
from tags import wrangling
from tags.models import MetaTagging, Tag
from tags.services import filter_tag_ids, work_filter_ids
from tags.wrangling import WRANGLERS_GROUP, WranglingError
from works.listing import refresh
from works.models import Chapter, PublicationStatus, Work, WorkAuthor

pytestmark = pytest.mark.django_db
F = Tag.Type.FREEFORM


def tag(name, tag_type=F, canonical=False, merger=None):
    return Tag.objects.create(name=name, type=tag_type, canonical=canonical, merger=merger)


@pytest.fixture
def au_tree():
    # Universo Alternativo > AU Cafeteria > AU Cafeteria Noturna, com sinônimos em cada nível
    au = tag("Universo Alternativo", canonical=True)
    cafe = tag("AU Cafeteria", canonical=True)
    night = tag("AU Cafeteria Noturna", canonical=True)
    MetaTagging.objects.create(meta=au, sub=cafe)
    MetaTagging.objects.create(meta=cafe, sub=night)
    return {
        "au": au,
        "cafe": cafe,
        "night": night,
        "au_syn": tag("Alternate Universe", merger=au),
        "cafe_syn": tag("Coffee Shop AU", merger=cafe),
        "night_syn": tag("Late Night Coffee AU", merger=night),
        "loose": tag("cafezinho"),
    }


@pytest.fixture
def wrangler(make_user):
    user = make_user("wrangler")
    user.groups.add(Group.objects.get(name=WRANGLERS_GROUP))
    return user


def published_work(author, *tags, title="Obra"):
    work = Work.objects.create(
        title=title, rating=Work.Rating.GENERAL, warnings=[Work.Warning.NONE_APPLY],
        status=PublicationStatus.PUBLISHED,
    )
    WorkAuthor.objects.create(work=work, pseud=author.default_pseud, status=WorkAuthor.Status.ACCEPTED)
    Chapter.objects.create(work=work, position=1, content="<p>x</p>", status=PublicationStatus.PUBLISHED)
    work.tags.set(tags)
    refresh([work.pk])
    return work


# --- Expansão para filtros ---


def test_filter_by_canonical_includes_synonyms_and_all_subtags(au_tree):
    t = au_tree
    expected = {t[k].pk for k in ("au", "cafe", "night", "au_syn", "cafe_syn", "night_syn")}
    assert filter_tag_ids(t["au"]) == expected


def test_filter_by_synonym_behaves_like_its_canonical(au_tree):
    assert filter_tag_ids(au_tree["cafe_syn"]) == filter_tag_ids(au_tree["cafe"])
    assert au_tree["au"].pk not in filter_tag_ids(au_tree["cafe"])  # não sobe para a metatag


def test_unwrangled_tag_only_matches_itself(au_tree):
    assert filter_tag_ids(au_tree["loose"]) == {au_tree["loose"].pk}


def test_work_is_findable_by_every_metatag_above(au_tree):
    t = au_tree
    found = work_filter_ids({t["night_syn"].pk, t["loose"].pk})
    assert found == {t["night"].pk, t["cafe"].pk, t["au"].pk}


# --- Regras de wrangling ---


def test_canonize_and_decanonize(wrangler):
    loose = tag("Fluff")
    assert wrangling.canonize(loose, wrangler)
    assert Tag.objects.get(pk=loose.pk).canonical
    assert wrangling.decanonize(loose, wrangler)
    assert not Tag.objects.get(pk=loose.pk).canonical
    assert ModerationAction.objects.filter(action="tag_canonize", object_id=loose.pk).exists()


def test_cannot_decanonize_with_links(au_tree, wrangler):
    with pytest.raises(WranglingError):
        wrangling.decanonize(au_tree["cafe"], wrangler)


def test_synonym_cannot_be_canonized(au_tree, wrangler):
    with pytest.raises(WranglingError):
        wrangling.canonize(au_tree["au_syn"], wrangler)


def test_merge_needs_canonical_of_same_type(wrangler):
    loose = tag("Ana")
    with pytest.raises(WranglingError):
        wrangling.make_synonym(loose, tag("Bia"), wrangler)
    with pytest.raises(WranglingError):
        wrangling.make_synonym(loose, tag("Ana Souza", Tag.Type.CHARACTER, canonical=True), wrangler)


def test_merging_a_canonical_moves_everything(au_tree, wrangler):
    t = au_tree
    fandom = tag("Fandom X", Tag.Type.FANDOM, canonical=True)
    new_home = tag("AU de Café", canonical=True)
    t["cafe"].fandoms.add(fandom)
    wrangling.make_synonym(t["cafe"], new_home, wrangler)

    cafe = Tag.objects.get(pk=t["cafe"].pk)
    assert not cafe.canonical and cafe.merger == new_home
    assert Tag.objects.get(pk=t["cafe_syn"].pk).merger == new_home  # sinônimo antigo foi junto
    assert MetaTagging.objects.filter(meta=t["au"], sub=new_home).exists()
    assert MetaTagging.objects.filter(meta=new_home, sub=t["night"]).exists()
    assert not MetaTagging.objects.filter(meta=cafe).exists() and not MetaTagging.objects.filter(sub=cafe).exists()
    assert list(new_home.fandoms.all()) == [fandom]
    # Filtrar pela metatag continua achando tudo
    assert t["cafe_syn"].pk in filter_tag_ids(t["au"])


def test_metatag_cycle_is_blocked(au_tree, wrangler):
    with pytest.raises(WranglingError):
        wrangling.add_metatag(au_tree["au"], au_tree["night"], wrangler)  # night acima de au: ciclo


def test_fandom_links(wrangler):
    fandom = tag("Fandom X", Tag.Type.FANDOM, canonical=True)
    character = tag("Ana", Tag.Type.CHARACTER, canonical=True)
    assert wrangling.add_fandom(character, fandom, wrangler)
    assert not wrangling.add_fandom(character, fandom, wrangler)  # repetido não duplica
    with pytest.raises(WranglingError):
        wrangling.add_fandom(fandom, fandom, wrangler)
    with pytest.raises(WranglingError):
        wrangling.add_fandom(character, tag("Não fandom", Tag.Type.CHARACTER, canonical=True), wrangler)
    assert wrangling.remove_fandom(character, fandom, wrangler)


def test_find_canonical_accepts_synonym(au_tree):
    assert wrangling.find_canonical("coffee shop au", F) == au_tree["cafe"]
    with pytest.raises(WranglingError):
        wrangling.find_canonical("cafezinho", F)
    with pytest.raises(WranglingError):
        wrangling.find_canonical("não existe", F)


# --- Páginas ---


def test_tag_page_lists_works_from_synonyms_and_subtags(client, au_tree, make_user):
    author = make_user("autora")
    published_work(author, au_tree["night_syn"], title="Noite no café")
    published_work(author, au_tree["loose"], title="Só cafezinho")
    content = client.get(reverse("tags:detail", args=[au_tree["au"].pk])).content.decode()
    assert "Noite no café" in content
    assert "Só cafezinho" not in content


def test_tag_page_hides_restricted_works_from_visitors(client, au_tree, make_user):
    work = published_work(make_user("autora"), au_tree["au"], title="Secreta")
    Work.objects.filter(pk=work.pk).update(restricted=True)
    refresh([work.pk])
    assert "Secreta" not in client.get(reverse("tags:detail", args=[au_tree["au"].pk])).content.decode()


def test_autocomplete_suggests_canonicals_even_from_synonyms(client, au_tree):
    # "coffee" só existe nos sinônimos; a sugestão é sempre a canônica
    results = client.get(reverse("tags:autocomplete"), {"q": "coffee", "tipo": F}).json()["results"]
    assert sorted(results) == ["AU Cafeteria", "AU Cafeteria Noturna"]
    results = client.get(reverse("tags:autocomplete"), {"q": "caf", "tipo": F}).json()["results"]
    assert "cafezinho" not in results
    assert client.get(reverse("tags:autocomplete"), {"q": "c"}).json()["results"] == []


def test_search_and_fandom_index(client):
    tag("Fandom Canônico", Tag.Type.FANDOM, canonical=True)
    tag("Fandom solto", Tag.Type.FANDOM)
    assert "Fandom Canônico" in client.get(reverse("tags:fandoms")).content.decode()
    assert "Fandom solto" not in client.get(reverse("tags:fandoms")).content.decode()
    found = client.get(reverse("tags:search"), {"q": "fandom", "canonicas": "0"}).content.decode()
    assert "Fandom solto" in found


def test_wrangling_requires_role(client, make_user, wrangler):
    url = reverse("tags:wrangling")
    assert client.get(url).status_code == 302  # visitante vai para o login
    client.force_login(make_user("comum"))
    assert client.get(url).status_code == 403
    client.force_login(wrangler)
    assert client.get(url).status_code == 200


def test_bulk_canonize_and_merge(client, wrangler):
    first, second, third = tag("Angst"), tag("angústia"), tag("Muito Angst")
    client.force_login(wrangler)
    client.post(reverse("tags:bulk"), {"tag_ids": [first.pk], "op": "canonize"})
    client.post(reverse("tags:bulk"), {"tag_ids": [second.pk, third.pk], "op": "merge", "target": "angst"})
    assert Tag.objects.get(pk=first.pk).canonical
    assert set(Tag.objects.filter(merger=first).values_list("pk", flat=True)) == {second.pk, third.pk}


def test_bulk_link_to_fandom(client, wrangler):
    fandom = tag("Fandom X", Tag.Type.FANDOM, canonical=True)
    character = tag("Ana", Tag.Type.CHARACTER, canonical=True)
    client.force_login(wrangler)
    client.post(reverse("tags:bulk"), {"tag_ids": [character.pk], "op": "fandom", "fandom_target": "Fandom X"})
    assert list(character.fandoms.all()) == [fandom]


def test_wrangle_page_operations(client, wrangler, au_tree):
    client.force_login(wrangler)
    url = reverse("tags:wrangle", args=[au_tree["loose"].pk])
    assert client.get(url).status_code == 200
    client.post(url, {"op": "merge", "target": "AU Cafeteria"})
    assert Tag.objects.get(pk=au_tree["loose"].pk).merger == au_tree["cafe"]
    cafe_url = reverse("tags:wrangle", args=[au_tree["cafe"].pk])
    client.post(cafe_url, {"op": "remove_meta", "other": au_tree["au"].pk})
    assert not MetaTagging.objects.filter(meta=au_tree["au"], sub=au_tree["cafe"]).exists()
    response = client.post(cafe_url, {"op": "add_sub", "target": "Universo Alternativo"}, follow=True)
    assert "ciclo" not in response.content.decode()  # sem a ligação antiga, não há ciclo
    assert MetaTagging.objects.filter(meta=au_tree["cafe"], sub=au_tree["au"]).exists()


def test_work_page_links_tags(client, au_tree, make_user):
    work = published_work(make_user("autora"), au_tree["cafe"])
    content = client.get(reverse("works:detail", args=[work.pk])).content.decode()
    assert reverse("tags:detail", args=[au_tree["cafe"].pk]) in content


def test_admin_grants_wrangler_role(admin_client, make_user):
    user = make_user("futura")
    admin_client.post(
        reverse("admin:accounts_user_changelist"), {"action": "grant_wrangler", "_selected_action": [user.pk]}
    )
    assert User.objects.get(pk=user.pk).has_perm("tags.wrangle")
