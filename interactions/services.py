import hashlib
import re

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from works.listing import queue_refresh
from works.services import user_can_edit

from . import counters
from .models import Comment, Kudos

BOT_RE = re.compile(r"bot|crawl|spider|slurp|preview|fetch", re.IGNORECASE)


def can_interact(user):
    return user.is_authenticated and user.is_active and user.is_approved


def anonymous_hash(value):
    # Nunca guardamos IP ou sessão puros, só um resumo irreversível
    return hashlib.sha256(f"{settings.SECRET_KEY}:{value}".encode()).hexdigest()[:32]


# --- Acessos ---


def register_hit(request, work):
    if BOT_RE.search(request.META.get("HTTP_USER_AGENT", "")):
        return False
    if request.user.is_authenticated:
        if user_can_edit(request.user, work):
            return False  # autor lendo a própria obra não conta
        visitor = f"u{request.user.pk}"
    else:
        visitor = anonymous_hash(request.META.get("REMOTE_ADDR", ""))
    return counters.register_hit(work.pk, visitor)


def total_hits(work):
    return work.hit_count + counters.pending_hits(work.pk)


# --- Kudos ---


def guest_key(request):
    if not request.session.session_key:
        request.session.save()
    return anonymous_hash(request.session.session_key)


def give_kudos(request, work):
    """Retorna 'ok', 'already' ou 'own'."""
    user = request.user
    if user.is_authenticated:
        if user_can_edit(user, work):
            return "own"
        if Kudos.objects.filter(work=work, user=user).exists() or counters.kudos_in_queue(work.pk, user_id=user.pk):
            return "already"
        return "ok" if counters.queue_kudos(work.pk, user_id=user.pk) else "already"
    key = guest_key(request)
    if Kudos.objects.filter(work=work, guest_key=key).exists():
        return "already"
    return "ok" if counters.queue_kudos(work.pk, guest_key=key) else "already"


def kudos_summary(work):
    names = list(
        Kudos.objects.filter(work=work, user__isnull=False)
        .select_related("user")
        .order_by("-created_at")
        .values_list("user__username", flat=True)[:50]
    )
    total = Kudos.objects.filter(work=work).count() + counters.pending_kudos(work.pk)
    guests = Kudos.objects.filter(work=work, user__isnull=True).count()
    return {"total": total, "names": names, "guests": guests}


# --- Comentários ---


def comment_rate_exceeded(user):
    key = f"comments:{user.pk}:{int(timezone.now().timestamp() // 3600)}"
    cache.add(key, 0, timeout=3700)
    return cache.incr(key) > settings.COMMENTS_PER_HOUR


@transaction.atomic
def add_comment(chapter, pseud, content, parent=None):
    from .tasks import send_comment_email

    comment = Comment.objects.create(chapter=chapter, pseud=pseud, content=content, parent=parent)
    queue_refresh([chapter.work_id])
    transaction.on_commit(lambda: send_comment_email.delay(comment.pk))
    return comment


def can_delete_comment(user, comment):
    if not user.is_authenticated:
        return False
    own = comment.pseud_id and comment.pseud.user_id == user.pk
    return bool(own or user.is_staff or user_can_edit(user, comment.chapter.work))


def can_edit_comment(user, comment):
    return user.is_authenticated and not comment.deleted and comment.pseud_id and comment.pseud.user_id == user.pk


@transaction.atomic
def delete_comment(comment):
    work_id = comment.chapter.work_id
    if comment.replies.exists():
        comment.deleted = True
        comment.content = ""
        comment.save(update_fields=["deleted", "content"])
    else:
        comment.delete()
    queue_refresh([work_id])


def comment_tree(chapter, viewer):
    """Lista achatada (comentário, profundidade) na ordem da conversa."""
    comments = list(chapter.comments.select_related("pseud__user").order_by("created_at"))
    children = {}
    for comment in comments:
        children.setdefault(comment.parent_id, []).append(comment)
    # Calcula uma vez só, em vez de uma consulta por comentário
    moderates = viewer.is_authenticated and (viewer.is_staff or user_can_edit(viewer, chapter.work))
    flat = []

    def walk(parent_id, depth):
        for comment in children.get(parent_id, []):
            own = viewer.is_authenticated and comment.pseud_id and comment.pseud.user_id == viewer.pk
            comment.can_delete = bool(own or moderates)
            comment.can_edit = bool(own and not comment.deleted)
            flat.append((comment, min(depth, 5)))
            walk(comment.pk, depth + 1)

    walk(None, 0)
    return flat
