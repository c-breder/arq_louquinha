import pytest
from django.db import IntegrityError

from works.models import Chapter, Work, WorkAuthor
from works.text import count_words


def test_count_words_ignores_html_and_entities():
    text = "<p>Olá, <em>mundo</em>!</p><p>Um guarda-chuva d'água &amp; mais&nbsp;duas</p>"
    assert count_words(text) == 7


def test_count_words_does_not_glue_paragraphs():
    assert count_words("<p>fim</p><p>Início</p>") == 2


def test_count_words_empty():
    assert count_words("") == 0
    assert count_words(None) == 0


@pytest.mark.django_db
def test_authors_only_lists_accepted_coauthors(make_user):
    owner = make_user("autora").default_pseud
    invited = make_user("convidada").default_pseud
    work = Work.objects.create(title="Obra", rating=Work.Rating.GENERAL, warnings=[Work.Warning.NONE_APPLY])
    WorkAuthor.objects.create(work=work, pseud=owner, status=WorkAuthor.Status.ACCEPTED)
    WorkAuthor.objects.create(work=work, pseud=invited)
    assert list(work.authors) == [owner]


@pytest.mark.django_db
def test_chapter_position_is_unique_per_work():
    work = Work.objects.create(title="Obra", rating=Work.Rating.TEEN, warnings=[Work.Warning.NONE_APPLY])
    Chapter.objects.create(work=work, position=1, content="<p>a</p>")
    with pytest.raises(IntegrityError):
        Chapter.objects.create(work=work, position=1, content="<p>b</p>")
