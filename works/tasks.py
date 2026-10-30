from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from .models import Chapter, PublicationStatus, Work, WorkAuthor, WorkImage
from .services import publish_chapter, publish_work, refresh_work_stats


@shared_task
def publish_scheduled():
    # Roda a cada minuto pelo beat
    now = timezone.now()
    for work in Work.objects.filter(status=PublicationStatus.SCHEDULED, scheduled_for__lte=now):
        publish_work(work, work.scheduled_for)
        refresh_work_stats(work)
    due = Chapter.objects.filter(status=PublicationStatus.SCHEDULED, scheduled_for__lte=now).select_related("work")
    for chapter in due:
        publish_chapter(chapter, chapter.scheduled_for)
        refresh_work_stats(chapter.work)


@shared_task
def refresh_listings(work_ids):
    from .listing import refresh

    refresh(work_ids)


@shared_task
def rebuild_all_listings():
    # Rede de segurança noturna: corrige qualquer atualização que tenha se perdido
    from .listing import rebuild_all

    rebuild_all()


@shared_task
def cleanup_unused_images():
    # Apaga imagens enviadas há mais de N dias que não aparecem em nenhum capítulo
    limit = timezone.now() - timedelta(days=settings.UNUSED_IMAGE_DAYS)
    for image in WorkImage.objects.filter(created_at__lt=limit):
        if not Chapter.objects.filter(content__contains=image.file.url).exists():
            image.delete()


@shared_task
def send_coauthor_invite_email(authorship_id):
    authorship = WorkAuthor.objects.select_related("work", "pseud__user", "invited_by").filter(pk=authorship_id).first()
    if authorship is None or authorship.status != WorkAuthor.Status.PENDING:
        return
    user = authorship.pseud.user
    with translation.override(user.language):
        subject = _("Convite de coautoria")
        body = _(
            "Olá, %(username)s!\n\n%(inviter)s convidou você para ser coautor(a) de \"%(title)s\".\n"
            "Para aceitar ou recusar, acesse: %(path)s"
        ) % {
            "username": user.username,
            "inviter": authorship.invited_by.username if authorship.invited_by else "?",
            "title": authorship.work.title,
            "path": reverse("works:invitations"),
        }
    send_mail(f"[{settings.SITE_NAME}] {subject}", body, None, [user.email])
