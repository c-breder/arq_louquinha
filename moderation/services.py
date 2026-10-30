from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from .models import ModerationAction, Report

Action = ModerationAction.Action


def _refresh_listing(target):
    from interactions.models import Comment
    from works.listing import queue_refresh
    from works.models import Work

    if isinstance(target, Work):
        queue_refresh([target.pk])
    elif isinstance(target, Comment):
        queue_refresh([target.chapter.work_id])


@transaction.atomic
def set_hidden(target, hidden, actor, report=None):
    """Oculta ou reexibe obra, comentário ou mensagem (nada é apagado)."""
    if not hasattr(target, "hidden_by_moderator") or target.hidden_by_moderator == hidden:
        return False
    target.hidden_by_moderator = hidden
    target.save(update_fields=["hidden_by_moderator"])
    log_action(actor, Action.HIDE if hidden else Action.UNHIDE, target, report=report)
    _refresh_listing(target)
    return True


def owners_of(target):
    """Quem responde pelo conteúdo denunciado."""
    from django.contrib.auth import get_user_model

    from interactions.models import Comment
    from messaging.models import Message
    from works.models import Work, WorkAuthor

    if isinstance(target, Work):
        return list(
            get_user_model().objects.filter(
                pseuds__authorships__work=target, pseuds__authorships__status=WorkAuthor.Status.ACCEPTED
            )
        )
    if isinstance(target, Comment):
        return [target.pseud.user] if target.pseud_id else []
    if isinstance(target, Message):
        return [target.sender]
    if isinstance(target, get_user_model()):
        return [target]
    return []


@transaction.atomic
def set_suspended(user, suspended, actor, report=None):
    if user.is_staff or user.is_active != suspended:
        return False
    user.is_active = not suspended
    user.save(update_fields=["is_active"])
    log_action(actor, Action.SUSPEND if suspended else Action.UNSUSPEND, user, report=report)
    return True


def close_report(report, actor, status, note=""):
    report.status = status
    report.handled_by = actor
    report.handled_at = timezone.now()
    if note:
        report.resolution_note = note
    report.save(update_fields=["status", "handled_by", "handled_at", "resolution_note"])


def log_action(actor, action, target, note="", report=None):
    return ModerationAction.objects.create(
        actor=actor,
        action=action,
        content_type=ContentType.objects.get_for_model(target),
        object_id=target.pk,
        note=note,
        report=report,
    )
