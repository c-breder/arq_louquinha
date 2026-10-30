from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from tags.models import Tag
from tags.services import refresh_use_counts, resolve_tags

from .listing import queue_refresh
from .models import Chapter, PublicationStatus, Work, WorkAuthor
from .sanitize import clean_html

TAG_FIELDS = {
    "fandom_tags": Tag.Type.FANDOM,
    "relationship_tags": Tag.Type.RELATIONSHIP,
    "character_tags": Tag.Type.CHARACTER,
    "freeform_tags": Tag.Type.FREEFORM,
}


# --- Permissões ---


def user_can_edit(user, work):
    if not user.is_authenticated:
        return False
    return WorkAuthor.objects.filter(work=work, pseud__user=user, status=WorkAuthor.Status.ACCEPTED).exists()


def images_visible(work):
    # Se nenhum autor tem o nível "Imagens", as imagens ficam ocultas (sem apagar)
    User = get_user_model()
    return User.objects.filter(
        pseuds__authorships__work=work,
        pseuds__authorships__status=WorkAuthor.Status.ACCEPTED,
        media_level__gte=User.MediaLevel.IMAGES,
    ).exists()


def render_html(html, work):
    return clean_html(html, allow_images=images_visible(work))


# --- Publicação ---


def publish_work(work, when=None):
    when = when or timezone.now()
    if work.status != PublicationStatus.PUBLISHED:
        work.status = PublicationStatus.PUBLISHED
        work.published_at = when
        work.scheduled_for = None
        work.save(update_fields=["status", "published_at", "scheduled_for", "updated_at"])
    first = work.chapters.order_by("position").first()
    if first and first.status != PublicationStatus.PUBLISHED:
        publish_chapter(first, when)


def publish_chapter(chapter, when=None):
    when = when or timezone.now()
    chapter.status = PublicationStatus.PUBLISHED
    chapter.published_at = when
    chapter.scheduled_for = None
    chapter.save(update_fields=["status", "published_at", "scheduled_for", "updated_at"])
    if chapter.work.status != PublicationStatus.PUBLISHED:
        publish_work(chapter.work, when)


def apply_action(obj, action, scheduled_for=None):
    """Aplica 'draft', 'publish' ou 'schedule'. O que já está publicado continua publicado."""
    if obj.status == PublicationStatus.PUBLISHED:
        return
    if action == "publish":
        obj.status = PublicationStatus.PUBLISHED
        obj.published_at = timezone.now()
        obj.scheduled_for = None
    elif action == "schedule":
        obj.status = PublicationStatus.SCHEDULED
        obj.scheduled_for = scheduled_for
    else:
        obj.status = PublicationStatus.DRAFT
        obj.scheduled_for = None


def sync_work_with_chapter(work, chapter):
    # Capítulo publicado/agendado numa obra ainda não publicada puxa a obra junto
    if work.status == PublicationStatus.PUBLISHED:
        return
    if chapter.status == PublicationStatus.PUBLISHED:
        publish_work(work, chapter.published_at)
    elif chapter.status == PublicationStatus.SCHEDULED:
        if work.status != PublicationStatus.SCHEDULED or chapter.scheduled_for < work.scheduled_for:
            work.status = PublicationStatus.SCHEDULED
            work.scheduled_for = chapter.scheduled_for
            work.save(update_fields=["status", "scheduled_for", "updated_at"])


def refresh_work_stats(work):
    chapters = work.chapters.all()
    if work.status == PublicationStatus.PUBLISHED:
        chapters = chapters.filter(status=PublicationStatus.PUBLISHED)
    work.word_count = chapters.aggregate(total=Sum("word_count"))["total"] or 0
    fields = ["word_count", "updated_at"]
    if work.is_complete:
        work.expected_chapters = work.chapters.count()
        fields.append("expected_chapters")
    work.save(update_fields=fields)
    queue_refresh([work.pk])


# --- Salvar obra e capítulos ---


@transaction.atomic
def save_work(work_form, user, chapter_form=None, action="draft", scheduled_for=None):
    work = work_form.save(commit=False)
    is_new = work.pk is None
    apply_action(work, action, scheduled_for)
    work.save()

    old_tag_ids = set(work.tags.values_list("pk", flat=True)) if not is_new else set()
    new_tags = []
    for field, tag_type in TAG_FIELDS.items():
        new_tags += resolve_tags(work_form.cleaned_data[field], tag_type)
    work.tags.set(new_tags)
    refresh_use_counts(old_tag_ids | {tag.pk for tag in new_tags})

    # Pseudônimos do próprio usuário; coautores não são mexidos
    chosen = set(work_form.cleaned_data["pseuds"])
    current = {
        authorship.pseud: authorship
        for authorship in work.authorships.filter(pseud__user=user).select_related("pseud")
    }
    for pseud in chosen:
        WorkAuthor.objects.update_or_create(work=work, pseud=pseud, defaults={"status": WorkAuthor.Status.ACCEPTED})
    for pseud, authorship in current.items():
        if pseud not in chosen:
            authorship.delete()

    if chapter_form is not None:
        chapter = chapter_form.save(commit=False)
        chapter.work = work
        chapter.position = 1
        apply_action(chapter, action, scheduled_for)
        chapter.save()
    elif action == "publish":
        publish_work(work, work.published_at)

    refresh_work_stats(work)
    return work


@transaction.atomic
def save_chapter(chapter_form, work, action="draft", scheduled_for=None):
    chapter = chapter_form.save(commit=False)
    if chapter.pk is None:
        chapter.work = work
        chapter.position = (work.chapters.aggregate(last=Max("position"))["last"] or 0) + 1
    apply_action(chapter, action, scheduled_for)
    chapter.save()
    sync_work_with_chapter(work, chapter)
    work.refresh_from_db()
    refresh_work_stats(work)
    return chapter


@transaction.atomic
def delete_chapter(chapter):
    work = chapter.work
    position = chapter.position
    chapter.delete()
    # Fecha o buraco na numeração (em ordem, para não colidir com a restrição única)
    for later in work.chapters.filter(position__gt=position).order_by("position"):
        later.position -= 1
        later.save(update_fields=["position"])
    refresh_work_stats(work)


@transaction.atomic
def delete_work(work):
    tag_ids = set(work.tags.values_list("pk", flat=True))
    work.delete()
    refresh_use_counts(tag_ids)


# --- Importação (PDF do AO3) ---


@transaction.atomic
def create_imported_work(user, imported):
    """Cria a obra como RASCUNHO, no pseudônimo padrão de quem importou. Devolve (obra, avisos)."""
    from django.core.exceptions import ValidationError

    from .text import count_words

    problems = list(imported.problems)
    work = Work.objects.create(
        title=imported.title or "Obra importada",
        summary=clean_html(imported.summary),
        notes=clean_html(imported.notes),
        end_notes=clean_html(imported.end_notes),
        language=imported.language,
        rating=imported.rating,
        warnings=imported.warnings,
        categories=imported.categories,
        is_complete=imported.is_complete,
        expected_chapters=imported.expected_chapters,
        status=PublicationStatus.DRAFT,
    )
    WorkAuthor.objects.create(work=work, pseud=user.default_pseud, status=WorkAuthor.Status.ACCEPTED)

    tags = []
    groups = [
        (imported.fandoms, Tag.Type.FANDOM),
        (imported.relationships, Tag.Type.RELATIONSHIP),
        (imported.characters, Tag.Type.CHARACTER),
        (imported.freeforms, Tag.Type.FREEFORM),
    ]
    for names, tag_type in groups:
        for name in names[:75]:
            try:
                tags += resolve_tags([name[:150]], tag_type)
            except ValidationError as error:
                problems.append(error.messages[0])  # tag que já existe com outro tipo
    work.tags.set(tags)

    for chapter in imported.chapters:
        content = clean_html(chapter.content)
        Chapter.objects.create(
            work=work,
            position=chapter.number,
            title=chapter.title[:255],
            summary=clean_html(chapter.summary),
            notes=clean_html(chapter.notes),
            content=content,
            end_notes=clean_html(chapter.end_notes),
            word_count=count_words(content),
            status=PublicationStatus.DRAFT,
        )
    refresh_use_counts({tag.pk for tag in tags})
    refresh_work_stats(work)
    return work, problems


# --- Coautoria ---


def invite_coauthor(work, pseud, invited_by):
    from .tasks import send_coauthor_invite_email

    authorship, created = WorkAuthor.objects.get_or_create(
        work=work, pseud=pseud, defaults={"status": WorkAuthor.Status.PENDING, "invited_by": invited_by}
    )
    if created:
        transaction.on_commit(lambda: send_coauthor_invite_email.delay(authorship.pk))
    return created


def leave_work(work, user):
    # Só sai se continuar havendo outro autor
    others = work.authorships.filter(status=WorkAuthor.Status.ACCEPTED).exclude(pseud__user=user)
    if not others.exists():
        return False
    work.authorships.filter(pseud__user=user).delete()
    queue_refresh([work.pk])
    return True
