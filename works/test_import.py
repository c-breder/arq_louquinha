from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from fpdf import FPDF

from tags.models import Tag
from works.importer import ImportProblem, parse_pdf
from works.models import PublicationStatus, Work

LONG = (
    "Era uma vez uma padaria no fim da rua, onde o cheiro de pao de queijo acordava o bairro inteiro "
    "antes do sol nascer e todo mundo sabia o nome de todo mundo."
)

AO3_MULTI = [
    "Cafe da Manha",
    "Posted originally on the Archive of Our Own at http://archiveofourown.org/works/123.",
    "Rating: Teen And Up Audiences",
    "Archive Warning: No Archive Warnings Apply",
    "Category: F/F",
    "Fandom: Fandom de Exemplo",
    "Relationship: Ana/Bia",
    "Character: Ana Souza, Bia Lima",
    "Additional Tags: Fluff, Slow Burn, Universo Alternativo - Cafeteria, Final Feliz, Primeiro Beijo, Amigas de Infancia",
    "Language: Português brasileiro",
    "Stats: Published: 2020-01-01 Completed: 2020-02-01 Chapters: 2/2 Words: 500",
    "Cafe da Manha",
    "by antiga_autora",
    "Summary",
    "Duas amigas e uma padaria.",
    "Notes",
    "Minha primeira fic, sejam gentis.",
    "Chapter 1: O Forno",
    "Chapter Notes",
    "Nota do primeiro capitulo.",
    "See the end of the chapter for more notes",
    LONG,
    "Ana chegou cedo.",
    LONG,
    "Chapter End Notes",
    "Obrigada por ler!",
    "Chapter 2",
    "O segundo dia comecou com chuva e cafe forte, e Bia ja estava no balcao contando moedas.",
    "Fim.",
    "Afterword",
    "End Notes",
    "Ate a proxima.",
    "Please drop by the Archive and comment to let the creator know if you enjoyed their work!",
]

AO3_ONESHOT = [
    "Uma Tarde",
    "Rating: General Audiences",
    "Archive Warning: Creator Chose Not To Use Archive Warnings",
    "Fandom: Fandom de Exemplo",
    "Language: English",
    "Stats: Published: 2021-05-05 Words: 300 Chapters: 1/1",
    "Uma Tarde",
    "by antiga_autora",
    "Summary",
    "Um resumo curto.",
    LONG,
    LONG,
]


def make_pdf(lines):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in lines:
        pdf.multi_cell(0, 6, line)
        pdf.ln(3)
    buffer = BytesIO(bytes(pdf.output()))
    return buffer


def upload(lines, name="obra.pdf"):
    return SimpleUploadedFile(name, make_pdf(lines).getvalue(), content_type="application/pdf")


# --- Leitura do PDF ---


def test_parse_multichapter_ao3_pdf():
    work = parse_pdf(make_pdf(AO3_MULTI))
    assert work.title == "Cafe da Manha"
    assert work.author == "antiga_autora"
    assert work.rating == "teen"
    assert work.warnings == ["none_apply"]
    assert work.categories == ["ff"]
    assert work.fandoms == ["Fandom de Exemplo"]
    assert work.characters == ["Ana Souza", "Bia Lima"]
    assert "Amigas de Infancia" in work.freeforms  # campo que quebrou em duas linhas
    assert work.language == "pt-br"
    assert work.is_complete and work.expected_chapters == 2
    assert "Duas amigas" in work.summary and "primeira fic" in work.notes
    assert "Ate a proxima" in work.end_notes
    assert [(c.number, c.title) for c in work.chapters] == [(1, "O Forno"), (2, "")]
    first = work.chapters[0]
    assert "Nota do primeiro" in first.notes and "padaria" not in first.notes
    assert first.content.count("<p>") == 3  # parágrafos longos reconstruídos
    assert "Obrigada por ler" in first.end_notes
    assert "Please drop by" not in work.chapters[1].content


def test_paragraphs_split_by_vertical_space_even_when_last_line_is_full():
    # A última linha deste parágrafo ocupa quase a largura toda (caso que a regra antiga juntava)
    full = (
        "A chuva batia nas janelas da biblioteca quando Helena encontrou o caderno esquecido entre dois volumes "
        "de poesia. As páginas estavam amareladas, e a letra era a mesma da carta que a avó guardava na gaveta."
    )
    lines = AO3_ONESHOT[:10] + [full, "Marina chegou molhada.", full, full]  # até "Um resumo curto."
    work = parse_pdf(make_pdf(lines))
    assert work.summary == "<p>Um resumo curto.</p>"
    assert work.chapters[0].content.count("<p>") == 4


def test_parse_oneshot_moves_text_out_of_summary():
    work = parse_pdf(make_pdf(AO3_ONESHOT))
    assert len(work.chapters) == 1
    assert work.summary == "<p>Um resumo curto.</p>"
    assert work.chapters[0].content.count("<p>") == 2
    assert work.language == "en" and work.rating == "general"


def test_unknown_format_becomes_single_chapter():
    work = parse_pdf(make_pdf(["Meu Texto Antigo", LONG, LONG]))
    assert not work.recognized
    assert len(work.chapters) == 1 and "padaria" in work.chapters[0].content
    assert any("Não reconheci" in problem for problem in work.problems)


def test_pdf_without_text_is_refused():
    pdf = FPDF()
    pdf.add_page()
    with pytest.raises(ImportProblem):
        parse_pdf(BytesIO(bytes(pdf.output())))


def test_garbage_is_refused():
    with pytest.raises(ImportProblem):
        parse_pdf(BytesIO(b"%PDF-1.4 isso nao e um pdf de verdade"))


# --- Botão "Importar obra" ---


@pytest.mark.django_db
def test_import_creates_draft_with_chapters_and_tags(client, make_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    author = make_user("autora")
    client.force_login(author)
    response = client.post(reverse("works:import"), {"file": upload(AO3_MULTI)})
    work = Work.objects.get()
    assert response.url == reverse("works:import_result", args=[work.pk])
    assert work.status == PublicationStatus.DRAFT
    assert list(work.authors) == [author.default_pseud]
    assert list(work.chapters.values_list("position", "title", "status")) == [(1, "O Forno", "draft"), (2, "", "draft")]
    assert work.word_count > 50
    assert Tag.objects.get(name="Ana/Bia").type == Tag.Type.RELATIONSHIP
    assert work.tags.filter(type=Tag.Type.FANDOM).count() == 1

    page = client.get(response.url).content.decode()
    assert "2 capítulos reconhecidos" in page and "O Forno" in page
    client.logout()
    assert client.get(reverse("works:detail", args=[work.pk])).status_code == 404  # rascunho


@pytest.mark.django_db
def test_import_reports_tag_conflicts(client, make_user):
    Tag.objects.create(name="Fluff", type=Tag.Type.CHARACTER)
    client.force_login(make_user("autora"))
    response = client.post(reverse("works:import"), {"file": upload(AO3_MULTI)}, follow=True)
    assert "Fluff" in response.content.decode() and "já existe como" in response.content.decode()
    assert not Work.objects.get().tags.filter(name="Fluff").exists()


@pytest.mark.django_db
def test_import_rejects_non_pdf_and_pending_users(client, make_user):
    client.force_login(make_user("autora"))
    fake = SimpleUploadedFile("obra.pdf", b"texto qualquer", content_type="application/pdf")
    response = client.post(reverse("works:import"), {"file": fake})
    assert "não é um PDF" in response.content.decode()
    client.force_login(make_user("pendente", approved=False))
    assert client.post(reverse("works:import"), {"file": upload(AO3_MULTI)}).status_code == 302
    assert not Work.objects.exists()


@pytest.mark.django_db
def test_import_rate_limit(client, make_user, settings):
    settings.IMPORTS_PER_HOUR = 1
    client.force_login(make_user("autora"))
    client.post(reverse("works:import"), {"file": upload(AO3_ONESHOT)})
    client.post(reverse("works:import"), {"file": upload(AO3_ONESHOT)})
    assert Work.objects.count() == 1


@pytest.mark.django_db
def test_only_author_sees_import_result(client, make_user):
    client.force_login(make_user("autora"))
    client.post(reverse("works:import"), {"file": upload(AO3_ONESHOT)})
    work = Work.objects.get()
    client.force_login(make_user("outra"))
    assert client.get(reverse("works:import_result", args=[work.pk])).status_code == 403
