"""Lê um PDF baixado do AO3 e separa metadados, resumo, notas e capítulos."""

import re
from collections import Counter
from dataclasses import dataclass, field
from html import escape

from django.utils.translation import gettext as _
from pypdf import PdfReader

from .models import Work

MAX_PAGES = 3000

RATINGS = {
    "general audiences": Work.Rating.GENERAL,
    "teen and up audiences": Work.Rating.TEEN,
    "mature": Work.Rating.MATURE,
    "explicit": Work.Rating.EXPLICIT,
    "not rated": Work.Rating.NOT_RATED,
}
WARNINGS = {
    "creator chose not to use archive warnings": Work.Warning.CHOSE_NOT_TO_WARN,
    "choose not to use archive warnings": Work.Warning.CHOSE_NOT_TO_WARN,
    "graphic depictions of violence": Work.Warning.VIOLENCE,
    "major character death": Work.Warning.MAJOR_CHARACTER_DEATH,
    "no archive warnings apply": Work.Warning.NONE_APPLY,
    "rape/non-con": Work.Warning.NON_CON,
    "underage": Work.Warning.UNDERAGE,
    "underage sex": Work.Warning.UNDERAGE,
}
CATEGORIES = {
    "f/f": Work.Category.FF,
    "f/m": Work.Category.FM,
    "gen": Work.Category.GEN,
    "m/m": Work.Category.MM,
    "multi": Work.Category.MULTI,
    "other": Work.Category.OTHER,
}
LANGUAGES = {
    "português brasileiro": "pt-br",
    "português europeu": "pt",
    "português": "pt",
    "english": "en",
    "español": "es",
    "français": "fr",
    "deutsch": "de",
    "italiano": "it",
    "日本語": "ja",
    "한국어": "ko",
    "中文-普通话 國語": "zh",
}

FIELD_RE = re.compile(
    r"^(Rating|Archive Warnings?|Categor(?:y|ies)|Fandoms?|Relationships?|Characters?|Additional Tags|"
    r"Language|Series|Collections|Stats):\s*(.*)$"
)
STATS_RE = re.compile(r"(Published|Updated|Completed|Words|Chapters|Comments|Kudos|Bookmarks|Hits):")
CHAPTERS_STAT_RE = re.compile(r"Chapters:\s*(\d+)/(\d+|\?)")
CHAPTER_RE = re.compile(r"^Chapter (\d+)(?::\s*(.*))?$")
SEE_END_RE = re.compile(r"^\(?See the end of the (?:chapter|work) for (?:more )?notes\.?\)?\.?$", re.IGNORECASE)
STOP_RE = re.compile(r"^(Please drop by the Archive|Works inspired by this one)", re.IGNORECASE)
NOISE_RE = re.compile(r"^(\d{1,4}|Posted originally on the Archive of Our Own.*|https?://\S+)$", re.IGNORECASE)
SENTENCE_END = tuple('.!?…"”»):')


class ImportProblem(Exception):
    """Erro que pode ser mostrado para a pessoa."""


@dataclass
class ImportedChapter:
    number: int
    title: str = ""
    summary: object = field(default_factory=list)
    notes: object = field(default_factory=list)
    content: object = field(default_factory=list)
    end_notes: object = field(default_factory=list)


@dataclass
class ImportedWork:
    title: str = ""
    author: str = ""
    rating: str = Work.Rating.NOT_RATED
    warnings: list = field(default_factory=list)
    categories: list = field(default_factory=list)
    fandoms: list = field(default_factory=list)
    relationships: list = field(default_factory=list)
    characters: list = field(default_factory=list)
    freeforms: list = field(default_factory=list)
    language: str = "pt-br"
    is_complete: bool = False
    expected_chapters: int | None = None
    summary: object = field(default_factory=list)
    notes: object = field(default_factory=list)
    end_notes: object = field(default_factory=list)
    chapters: list = field(default_factory=list)
    recognized: bool = True
    problems: list = field(default_factory=list)


# Nas seções, uma lista guarda linhas cruas do PDF; uma tupla guarda parágrafos já prontos.


# --- Texto do PDF ---


def page_lines(page):
    """Linhas da página; um espaço vertical maior que o normal vira linha em branco (novo parágrafo)."""
    chunks = []

    def visit(text, cm, tm, _font, _size):
        if text and text.strip():
            chunks.append((cm[3] * tm[5] + cm[5], text))

    page.extract_text(visitor_text=visit)
    rows = []
    for y, text in chunks:
        if rows and abs(rows[-1][0] - y) < 1.0:
            rows[-1][1] += text  # pedaços da mesma linha
        else:
            rows.append([y, text])
    gaps = [above[0] - below[0] for above, below in zip(rows, rows[1:]) if above[0] - below[0] > 0]
    # Espaço normal entre linhas = o menor espaço que se repete (o de dentro dos parágrafos)
    repeated = [gap for gap, count in Counter(round(gap * 2) / 2 for gap in gaps).items() if count >= 2]
    typical = min(repeated) if repeated else (min(gaps) if gaps else 0)
    lines, previous = [], None
    for y, text in rows:
        if previous is not None and typical and (previous - y > typical * 1.35 or y > previous):
            lines.append("")
        lines.append(" ".join(text.split()))
        previous = y
    return lines


def extract_lines(upload):
    try:
        reader = PdfReader(upload)
        if reader.is_encrypted:
            reader.decrypt("")
        if len(reader.pages) > MAX_PAGES:
            raise ImportProblem(_("O PDF tem páginas demais (máximo de %(max)d).") % {"max": MAX_PAGES})
        lines = []
        for page in reader.pages:
            # Sem posições (PDF incomum): cai na extração simples
            raw_lines = page_lines(page) or (page.extract_text() or "").splitlines()
            for raw in raw_lines:
                line = " ".join(raw.split())
                if not line:
                    lines.append("")  # linha em branco separa parágrafos
                elif not NOISE_RE.match(line):
                    lines.append(line)
    except ImportProblem:
        raise
    except Exception as error:
        raise ImportProblem(_("Não consegui ler esse arquivo como PDF.")) from error
    if sum(len(line) for line in lines) < 50:
        raise ImportProblem(_("O PDF não tem texto para ler (talvez seja escaneado, como uma foto das páginas)."))
    return lines


def paragraphs(lines, full_width):
    """Junta as linhas quebradas pelo PDF em parágrafos."""
    result, current = [], []

    def flush():
        if current:
            text = current[0]
            for line in current[1:]:
                text = text + line if text.endswith("-") else f"{text} {line}"
            result.append(text)
            current.clear()

    # Se o PDF tem espaço entre parágrafos, ele manda; senão, adivinha pela linha curta com pontuação
    has_gaps = "" in lines
    for line in lines:
        if line == "":
            flush()
            continue
        current.append(line)
        if not has_gaps and len(line) < 0.8 * full_width and line.endswith(SENTENCE_END):
            flush()
    flush()
    return result


def to_html(paragraph_list):
    return "".join(f"<p>{escape(text)}</p>" for text in paragraph_list)


def split_names(value):
    return [name.strip() for name in value.split(",") if name.strip()]


# --- Formato do AO3 ---


def parse_header(lines, work):
    """Lê Rating/Fandom/... e o título; devolve onde começa o corpo (ou None se não for AO3)."""
    start = next((i for i, line in enumerate(lines[:60]) if FIELD_RE.match(line)), None)
    if start is None:
        return None
    fields, current, index = {}, None, start
    while index < len(lines):
        line = lines[index]
        match = FIELD_RE.match(line)
        if match:
            current = match.group(1)
            fields[current] = match.group(2)
        elif line and current == "Stats" and STATS_RE.search(line):
            fields[current] += " " + line
        elif line and current and current != "Stats":
            fields[current] += " " + line  # campo que quebrou em mais de uma linha
        elif line:
            break
        index += 1

    def get(*names):
        return next((fields[name] for name in names if name in fields), "")

    work.rating = RATINGS.get(get("Rating").strip().lower(), Work.Rating.NOT_RATED)
    work.warnings = [
        WARNINGS[name.lower()] for name in split_names(get("Archive Warning", "Archive Warnings")) if name.lower() in WARNINGS
    ]
    work.categories = [
        CATEGORIES[name.lower()] for name in split_names(get("Category", "Categories")) if name.lower() in CATEGORIES
    ]
    work.fandoms = split_names(get("Fandom", "Fandoms"))
    work.relationships = split_names(get("Relationship", "Relationships"))
    work.characters = split_names(get("Character", "Characters"))
    work.freeforms = split_names(get("Additional Tags"))
    language = get("Language").strip()
    work.language = LANGUAGES.get(language.lower(), "other" if language else "pt-br")
    stats = CHAPTERS_STAT_RE.search(get("Stats"))
    if stats:
        written, planned = stats.groups()
        work.expected_chapters = int(planned) if planned.isdigit() else None
        work.is_complete = planned.isdigit() and int(written) == int(planned)
    if not work.warnings:
        work.warnings = [Work.Warning.CHOSE_NOT_TO_WARN]
        work.problems.append(_("Não achei os avisos do AO3; marquei “Autor optou por não usar avisos”."))
    if "Series" in fields or "Collections" in fields:
        work.problems.append(_("Séries e coleções do AO3 não são importadas; adicione aqui depois, se quiser."))

    # Depois dos campos: o título (uma ou mais linhas) e "by Autor"
    while index < len(lines) and not lines[index]:
        index += 1
    by_line = next((i for i in range(index, min(index + 8, len(lines))) if lines[i].startswith("by ")), None)
    if by_line is None:
        return index
    work.title = " ".join(line for line in lines[index:by_line] if line)
    work.author = lines[by_line][3:].strip()
    return by_line + 1


def split_lead(lead, width):
    """Resumo/notas sem marcador de fim: o 1º parágrafo fica, o resto é texto do capítulo."""
    parts = paragraphs(lead, width)
    return tuple(parts[:1]), tuple(parts[1:])


def parse_body(lines, work, width):
    chapters = []
    implicit = ImportedChapter(number=1)  # obra de capítulo único não tem "Chapter 1"
    mode = "preamble"
    current = None
    marked = set()  # seções que terminaram num "See the end of ... for notes"

    for line in lines:
        chapter = CHAPTER_RE.match(line)
        if mode != "afterword" and chapter and int(chapter.group(1)) == len(chapters) + 1:
            chapters.append(ImportedChapter(number=len(chapters) + 1, title=(chapter.group(2) or "").strip()))
            mode, current = "chapter", chapters[-1].content
        elif mode == "preamble" and line == "Summary":
            current = work.summary
        elif mode == "preamble" and line == "Notes":
            current = work.notes
        elif mode == "chapter" and line == "Chapter Summary":
            current = chapters[-1].summary
        elif mode == "chapter" and line == "Chapter Notes":
            current = chapters[-1].notes
        elif mode == "chapter" and line == "Chapter End Notes":
            current = chapters[-1].end_notes
        elif line == "Afterword":
            mode, current = "afterword", None
        elif mode == "afterword" and line == "End Notes":
            current = work.end_notes
        elif SEE_END_RE.match(line):
            if current is not None:
                marked.add(id(current))
            current = chapters[-1].content if chapters else implicit.content
        elif STOP_RE.match(line):
            current = None
        else:
            if current is None and mode == "preamble" and line:
                current = implicit.content
            if current is not None:
                current.append(line)

    # Texto que "vazou" para dentro do resumo/notas (não há título "Chapter Text") volta para o capítulo
    holders = [(implicit, work)] if not chapters else [(chapter, chapter) for chapter in chapters]
    for target, owner in holders:
        if any(target.content):  # só linhas em branco conta como vazio
            continue
        for key in ("notes", "summary"):
            lead = getattr(owner, key)
            if any(lead) and id(lead) not in marked:
                kept, moved = split_lead(lead, width)
                setattr(owner, key, kept)
                target.content = moved
                break
    work.chapters = chapters or ([implicit] if any(implicit.content) else [])


def parse_pdf(upload):
    lines = extract_lines(upload)
    work = ImportedWork()
    lengths = sorted(len(line) for line in lines if line)
    width = lengths[int(len(lengths) * 0.9)] if lengths else 80

    body_start = parse_header(lines, work)
    if body_start is None:
        work.recognized = False
        work.problems.append(
            _("Não reconheci o formato do AO3: importei o texto inteiro como um capítulo. Confira tudo na revisão.")
        )
        work.title = next((line for line in lines if line), "")
        work.warnings = [Work.Warning.CHOSE_NOT_TO_WARN]
        work.chapters = [ImportedChapter(number=1, content=lines)]
    else:
        parse_body(lines[body_start:], work, width)
    if not work.chapters:
        raise ImportProblem(_("Não achei o texto da obra nesse PDF."))
    if not work.fandoms:
        work.problems.append(_("Não achei o fandom. Adicione na revisão antes de publicar."))

    def html(value):
        return to_html(value if isinstance(value, tuple) else paragraphs(value, width))

    for section in ("summary", "notes", "end_notes"):
        setattr(work, section, html(getattr(work, section)))
    for chapter in work.chapters:
        for section in ("summary", "notes", "content", "end_notes"):
            setattr(chapter, section, html(getattr(chapter, section)))
    work.title = work.title[:255]
    return work
