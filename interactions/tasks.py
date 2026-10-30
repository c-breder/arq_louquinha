from collections import Counter

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db.models import F
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _

from works.listing import plain_text, refresh
from works.models import Work, WorkAuthor

from . import counters
from .models import Comment, Kudos


@shared_task
def flush_counters():
    """Grava no banco os acessos e kudos acumulados no Redis (roda a cada minuto)."""
    touched = set()
    for work_id, total in counters.take_pending_hits().items():
        if Work.objects.filter(pk=work_id).update(hit_count=F("hit_count") + total):
            touched.add(work_id)

    items = counters.take_pending_kudos()
    existing = set(Work.objects.filter(pk__in={item["work"] for item in items}).values_list("pk", flat=True))
    Kudos.objects.bulk_create(
        [
            Kudos(work_id=item["work"], user_id=item["user"], guest_key=item["guest"] or "")
            for item in items
            if item["work"] in existing
        ],
        ignore_conflicts=True,  # se alguém deixou kudos duas vezes, a segunda é ignorada
    )
    counters.settle_kudos_counts(Counter(item["work"] for item in items))
    touched |= existing
    if touched:
        refresh(touched)
    return len(touched)


@shared_task
def send_comment_email(comment_id):
    comment = Comment.objects.select_related("chapter__work", "pseud__user", "parent__pseud__user").filter(
        pk=comment_id
    ).first()
    if comment is None:
        return
    work = comment.chapter.work
    commenter = comment.pseud.user if comment.pseud_id else None
    recipients = {
        authorship.pseud.user
        for authorship in WorkAuthor.objects.filter(work=work, status=WorkAuthor.Status.ACCEPTED).select_related(
            "pseud__user"
        )
    }
    if comment.parent_id and comment.parent.pseud_id:
        recipients.add(comment.parent.pseud.user)
    path = reverse("works:chapter", args=[work.pk, comment.chapter.position]) + f"#comentario-{comment.pk}"
    for user in recipients:
        if user == commenter or not user.is_active:
            continue
        with translation.override(user.language):
            subject = _("Novo comentário em “%(title)s”") % {"title": work.title}
            body = _("%(name)s comentou:\n\n%(text)s\n\nVer no site: %(path)s") % {
                "name": comment.pseud.name if comment.pseud_id else "?",
                "text": plain_text(comment.content)[:1000],
                "path": path,
            }
        send_mail(f"[{settings.SITE_NAME}] {subject}", body, None, [user.email])

