from django.db import transaction
from django.utils import timezone

from moderation.models import ModerationAction
from moderation.services import log_action

from .tasks import send_approval_email


def approve_user(user, by):
    if user.is_approved:
        return False
    user.is_approved = True
    user.is_active = True
    user.approved_at = timezone.now()
    user.approved_by = by
    user.save(update_fields=["is_approved", "is_active", "approved_at", "approved_by"])
    log_action(by, ModerationAction.Action.APPROVE_ACCOUNT, user)
    transaction.on_commit(lambda: send_approval_email.delay(user.pk))
    return True


def reject_user(user, by, note=""):
    user.is_active = False
    user.save(update_fields=["is_active"])
    log_action(by, ModerationAction.Action.REJECT_ACCOUNT, user, note=note)


def get_orphan_user():
    from django.conf import settings

    from .models import User

    user, created = User.objects.get_or_create(
        username=settings.ORPHAN_USERNAME,
        defaults={"email": "orphan@orphan.invalid", "is_active": False, "is_approved": True},
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    return user


@transaction.atomic
def delete_pseud(pseud):
    """Apaga um pseudônimo que não é o padrão; obras, bookmarks e comentários vão para o padrão."""
    from interactions.models import Bookmark, Comment
    from works.models import WorkAuthor

    from works.listing import queue_refresh

    default = pseud.user.default_pseud
    queue_refresh(WorkAuthor.objects.filter(pseud=pseud).values_list("work_id", flat=True))
    for authorship in WorkAuthor.objects.filter(pseud=pseud):
        if WorkAuthor.objects.filter(work=authorship.work, pseud=default).exists():
            authorship.delete()
        else:
            authorship.pseud = default
            authorship.save(update_fields=["pseud"])
    for bookmark in Bookmark.objects.filter(pseud=pseud):
        if Bookmark.objects.filter(work=bookmark.work, pseud=default).exists():
            bookmark.delete()
        else:
            bookmark.pseud = default
            bookmark.save(update_fields=["pseud"])
    Comment.objects.filter(pseud=pseud).update(pseud=default)
    for series in pseud.series.all():
        series.pseuds.add(default)
    pseud.delete()


@transaction.atomic
def set_default_pseud(pseud):
    pseud.user.pseuds.filter(is_default=True).update(is_default=False)
    pseud.is_default = True
    pseud.save(update_fields=["is_default"])


@transaction.atomic
def delete_account(user, works_choice):
    """works_choice: 'orphan' (obras ficam na conta órfã) ou 'delete' (obras somem)."""
    from works.listing import queue_refresh
    from works.models import WorkAuthor, WorkImage
    from works.services import delete_work

    queue_refresh(WorkAuthor.objects.filter(pseud__user=user).values_list("work_id", flat=True))
    orphan_pseud = get_orphan_user().default_pseud if works_choice == "orphan" else None
    for authorship in WorkAuthor.objects.filter(pseud__user=user).select_related("work"):
        work = authorship.work
        if not type(work).objects.filter(pk=work.pk).exists():
            continue
        has_others = work.authorships.filter(status=WorkAuthor.Status.ACCEPTED).exclude(pseud__user=user).exists()
        if has_others or authorship.status != WorkAuthor.Status.ACCEPTED:
            authorship.delete()
        elif orphan_pseud:
            WorkAuthor.objects.get_or_create(
                work=work, pseud=orphan_pseud, defaults={"status": WorkAuthor.Status.ACCEPTED}
            )
            authorship.delete()
        else:
            delete_work(work)
    if orphan_pseud:
        # As imagens continuam aparecendo nas obras órfãs, e as coleções continuam no ar
        from challenges.models import Collection

        WorkImage.objects.filter(owner=user).update(owner=orphan_pseud.user)
        Collection.objects.filter(owner=user).update(owner=orphan_pseud.user)
    user.delete()


def export_user_data(user):
    """Tudo o que o site guarda sobre a pessoa, em formato simples (LGPD)."""
    from allauth.account.models import EmailAddress
    from interactions.models import Bookmark, Comment, Kudos
    from messaging.models import Message
    from works.models import Work, WorkAuthor

    works = (
        Work.objects.filter(authorships__pseud__user=user, authorships__status=WorkAuthor.Status.ACCEPTED)
        .distinct()
        .prefetch_related("tags", "chapters")
    )
    return {
        "exported_at": timezone.now(),
        "account": {
            "username": user.username,
            "email": user.email,
            "date_joined": user.date_joined,
            "last_login": user.last_login,
            "is_approved": user.is_approved,
            "adult_confirmed_at": user.adult_confirmed_at,
            "media_level": user.get_media_level_display(),
            "language": user.language,
            "hide_warnings": user.hide_warnings,
            "hide_explicit": user.hide_explicit,
        },
        "emails": [
            {"email": address.email, "verified": address.verified, "primary": address.primary}
            for address in EmailAddress.objects.filter(user=user)
        ],
        "pseuds": [
            {
                "name": pseud.name,
                "description": pseud.description,
                "is_default": pseud.is_default,
                "avatar": pseud.avatar.url if pseud.avatar else None,
            }
            for pseud in user.pseuds.all()
        ],
        "works": [
            {
                "id": work.pk,
                "title": work.title,
                "status": work.status,
                "rating": work.rating,
                "warnings": work.warnings,
                "categories": work.categories,
                "language": work.language,
                "summary": work.summary,
                "notes": work.notes,
                "end_notes": work.end_notes,
                "restricted": work.restricted,
                "is_complete": work.is_complete,
                "published_at": work.published_at,
                "tags": [{"name": tag.name, "type": tag.type} for tag in work.tags.all()],
                "chapters": [
                    {
                        "position": chapter.position,
                        "title": chapter.title,
                        "summary": chapter.summary,
                        "notes": chapter.notes,
                        "content": chapter.content,
                        "end_notes": chapter.end_notes,
                        "status": chapter.status,
                        "published_at": chapter.published_at,
                    }
                    for chapter in sorted(work.chapters.all(), key=lambda chapter: chapter.position)
                ],
            }
            for work in works
        ],
        "bookmarks": [
            {
                "work_id": bookmark.work_id,
                "work_title": bookmark.work.title,
                "notes": bookmark.notes,
                "tags": [tag.name for tag in bookmark.tags.all()],
                "is_private": bookmark.is_private,
                "is_rec": bookmark.is_rec,
                "created_at": bookmark.created_at,
            }
            for bookmark in Bookmark.objects.filter(pseud__user=user).select_related("work").prefetch_related("tags")
        ],
        "comments": [
            {
                "work_title": comment.chapter.work.title,
                "chapter": comment.chapter.position,
                "content": comment.content,
                "created_at": comment.created_at,
            }
            for comment in Comment.objects.filter(pseud__user=user).select_related("chapter__work")
        ],
        "kudos": [
            {"work_id": kudos.work_id, "work_title": kudos.work.title, "created_at": kudos.created_at}
            for kudos in Kudos.objects.filter(user=user).select_related("work")
        ],
        "images": [image.file.url for image in user.work_images.all()],
        "messages_sent": [
            {"to": message.conversation.other(user).username, "body": message.body, "created_at": message.created_at}
            for message in Message.objects.filter(sender=user).select_related(
                "conversation__user_a", "conversation__user_b"
            )
        ],
        "collections_owned": [
            {"slug": collection.slug, "title": collection.title} for collection in user.owned_collections.all()
        ],
    }


def set_media_level(user, level, by):
    if user.media_level == level:
        return False
    old_label = user.get_media_level_display()
    user.media_level = level
    user.save(update_fields=["media_level"])
    log_action(
        by,
        ModerationAction.Action.CHANGE_MEDIA_LEVEL,
        user,
        note=f"{old_label} → {user.get_media_level_display()}",
    )
    return True
