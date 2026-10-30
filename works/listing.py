import html
import re
import unicodedata
from collections import defaultdict

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.db import transaction
from django.db.models import Count, F, Func, IntegerField, Max, OuterRef, Prefetch, Subquery, TextField
from django.db.models.functions import Coalesce

from interactions.models import Bookmark, Comment, Kudos
from tags.models import MetaTagging, Tag

from .models import Chapter, PublicationStatus, Work, WorkAuthor, WorkListing

BATCH = 500
TAG_ORDER = [Tag.Type.FANDOM, Tag.Type.RELATIONSHIP, Tag.Type.CHARACTER, Tag.Type.FREEFORM]


class Unaccent(Func):
    function = "unaccent"
    output_field = TextField()


# Título e autores pesam mais que tags, que pesam mais que o resumo
SEARCH_VECTOR = (
    SearchVector(Unaccent(F("title")), weight="A", config="simple")
    + SearchVector(Unaccent(F("authors_text")), weight="A", config="simple")
    + SearchVector(Unaccent(F("tags_text")), weight="B", config="simple")
    + SearchVector(Unaccent(F("summary_text")), weight="C", config="simple")
)
UPDATE_FIELDS = [
    field.name for field in WorkListing._meta.concrete_fields if field.name not in ("work", "search_vector")
]


def _count(queryset, group_by):
    totals = queryset.order_by().values(group_by).annotate(total=Count("pk")).values("total")
    return Coalesce(Subquery(totals, output_field=IntegerField()), 0)


def _meta_graph():
    graph = defaultdict(set)
    for meta_id, sub_id in MetaTagging.objects.values_list("meta_id", "sub_id"):
        graph[sub_id].add(meta_id)
    return graph


def _with_ancestors(tag_ids, graph):
    found = set(tag_ids)
    stack = list(tag_ids)
    while stack:
        for meta_id in graph.get(stack.pop(), ()):
            if meta_id not in found:
                found.add(meta_id)
                stack.append(meta_id)
    return found


def plain_text(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]*>", " ", value or ""))).strip()


def build_rows(work_ids):
    graph = _meta_graph()
    published = PublicationStatus.PUBLISHED
    works = (
        Work.objects.filter(pk__in=work_ids)
        .annotate(
            kudos_total=_count(Kudos.objects.filter(work=OuterRef("pk")), "work"),
            bookmark_total=_count(Bookmark.objects.filter(work=OuterRef("pk"), is_private=False), "work"),
            comment_total=_count(
                Comment.objects.filter(chapter__work=OuterRef("pk"), hidden_by_moderator=False), "chapter__work"
            ),
            chapter_total=_count(Chapter.objects.filter(work=OuterRef("pk"), status=published), "work"),
            revised=Subquery(
                Chapter.objects.filter(work=OuterRef("pk"), status=published)
                .order_by()
                .values("work")
                .annotate(last=Max("published_at"))
                .values("last")
            ),
        )
        .prefetch_related(
            "tags",
            Prefetch(
                "authorships",
                queryset=WorkAuthor.objects.filter(status=WorkAuthor.Status.ACCEPTED)
                .select_related("pseud__user")
                .order_by("created_at"),
                to_attr="accepted_authorships",
            ),
        )
    )
    rows = []
    for work in works:
        tags = sorted(work.tags.all(), key=lambda tag: (TAG_ORDER.index(tag.type), tag.name.lower()))
        canonical = {tag.merger_id or tag.pk for tag in tags if tag.merger_id or tag.canonical}
        loose = {tag.pk for tag in tags if not tag.merger_id and not tag.canonical}
        authors = [
            {"name": str(authorship.pseud), "username": authorship.pseud.user.username}
            for authorship in work.accepted_authorships
        ]
        rows.append(
            WorkListing(
                work_id=work.pk,
                visible=work.status == published and not work.hidden_by_moderator,
                restricted=work.restricted,
                title=work.title,
                rating=work.rating,
                warnings=work.warnings,
                categories=work.categories,
                language=work.language,
                is_complete=work.is_complete,
                word_count=work.word_count,
                chapter_count=work.chapter_total,
                expected_chapters=work.expected_chapters,
                published_at=work.published_at,
                revised_at=work.revised or work.published_at,
                kudos_count=work.kudos_total,
                hit_count=work.hit_count,
                bookmark_count=work.bookmark_total,
                comment_count=work.comment_total,
                filter_ids=sorted(_with_ancestors(canonical, graph) | loose),
                card={
                    "authors": authors,
                    "tags": {tag_type: [[tag.pk, tag.name] for tag in tags if tag.type == tag_type] for tag_type in TAG_ORDER},
                    "summary": work.summary,
                },
                authors_text=" ".join(author["name"] for author in authors),
                tags_text=" ".join(tag.name for tag in tags),
                summary_text=plain_text(work.summary),
            )
        )
    return rows


def refresh(work_ids):
    ids = sorted(set(work_ids))
    for start in range(0, len(ids), BATCH):
        chunk = ids[start : start + BATCH]
        rows = build_rows(chunk)
        WorkListing.objects.bulk_create(rows, update_conflicts=True, unique_fields=["work"], update_fields=UPDATE_FIELDS)
        WorkListing.objects.filter(work_id__in=chunk).update(search_vector=SEARCH_VECTOR)
    return len(ids)


def rebuild_all():
    return refresh(Work.objects.values_list("pk", flat=True))


def queue_refresh(work_ids):
    # Depois do commit, para o worker ler os dados já gravados
    from .tasks import refresh_listings

    ids = sorted(set(work_ids))
    if not ids:
        return
    if settings.LISTING_REFRESH_SYNC:
        refresh(ids)
    else:
        transaction.on_commit(lambda: refresh_listings.delay(ids))


def works_with_tags(tag_ids):
    return Work.tags.through.objects.filter(tag_id__in=tag_ids).values_list("work_id", flat=True).distinct()


# --- Busca ---


def strip_accents(text):
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def text_query(text):
    """Cada palavra vira prefixo ('cafe' acha 'cafeteria'); '-palavra' exclui."""
    parts = []
    for term in re.findall(r"-?\w+", strip_accents(text))[:12]:
        word = term.lstrip("-")
        if word:
            parts.append(("!" if term.startswith("-") else "") + f"{word}:*")
    if not any(not part.startswith("!") for part in parts):
        return None
    return SearchQuery(" & ".join(parts), config="simple", search_type="raw")


def tag_filter_id(tag):
    # Sinônimo filtra pela canônica; tag não organizada filtra por ela mesma
    return tag.merger_id or tag.pk


def base_listings(user):
    listings = WorkListing.objects.filter(visible=True)
    if not user.is_authenticated:
        listings = listings.filter(restricted=False)
    elif user.hide_explicit:
        listings = listings.exclude(rating="explicit")
    return listings


def apply_text_search(listings, text, rank=False):
    query = text_query(text)
    if query is None:
        return listings
    listings = listings.filter(search_vector=query)
    if rank:
        listings = listings.annotate(rank=SearchRank("search_vector", query))
    return listings
