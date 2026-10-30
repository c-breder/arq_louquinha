from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from works.listing import base_listings, queue_refresh
from works.models import Chapter, PublicationStatus, Work

from . import services
from .forms import BookmarkForm, CommentForm
from .models import Bookmark, Comment


def readable_work(request, work_id):
    work = get_object_or_404(Work, pk=work_id, status=PublicationStatus.PUBLISHED, hidden_by_moderator=False)
    if work.restricted and not request.user.is_authenticated:
        raise Http404
    return work


def chapter_url(chapter, anchor=""):
    return reverse("works:chapter", args=[chapter.work_id, chapter.position]) + anchor


# --- Kudos ---


@require_POST
def give_kudos(request, work_id):
    work = readable_work(request, work_id)
    result = services.give_kudos(request, work)
    text = {
        "ok": _("Obrigado pelos kudos! 💛"),
        "already": _("Você já deixou kudos nesta obra."),
        "own": _("Você não pode deixar kudos na sua própria obra."),
    }[result]
    (messages.success if result == "ok" else messages.info)(request, text)
    return redirect(request.POST.get("next") or reverse("works:detail", args=[work.pk]))


# --- Comentários ---


@login_required
@require_POST
def add_comment(request, work_id, position):
    work = readable_work(request, work_id)
    chapter = get_object_or_404(Chapter, work=work, position=position, status=PublicationStatus.PUBLISHED)
    if not services.can_interact(request.user):
        raise PermissionDenied
    form = CommentForm(request.POST, user=request.user)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect(chapter_url(chapter, "#comentarios"))
    if services.comment_rate_exceeded(request.user):
        messages.error(request, _("Você comentou demais na última hora. Tente mais tarde."))
        return redirect(chapter_url(chapter, "#comentarios"))
    parent = None
    if form.cleaned_data.get("parent"):
        parent = get_object_or_404(Comment, pk=form.cleaned_data["parent"], chapter=chapter)
    comment = services.add_comment(chapter, form.cleaned_data["pseud"], form.cleaned_data["content"], parent)
    messages.success(request, _("Comentário publicado."))
    return redirect(chapter_url(chapter, f"#comentario-{comment.pk}"))


@login_required
def edit_comment(request, comment_id):
    comment = get_object_or_404(Comment.objects.select_related("chapter", "pseud"), pk=comment_id)
    if not services.can_edit_comment(request.user, comment):
        raise PermissionDenied
    form = CommentForm(request.POST or None, instance=comment, user=request.user)
    if request.method == "POST" and form.is_valid():
        comment = form.save(commit=False)
        comment.edited_at = timezone.now()
        comment.save()
        return redirect(chapter_url(comment.chapter, f"#comentario-{comment.pk}"))
    return render(request, "interactions/comment_edit.html", {"form": form, "comment": comment})


@login_required
@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment.objects.select_related("chapter__work", "pseud"), pk=comment_id)
    if not services.can_delete_comment(request.user, comment):
        raise PermissionDenied
    chapter = comment.chapter
    services.delete_comment(comment)
    messages.success(request, _("Comentário apagado."))
    return redirect(chapter_url(chapter, "#comentarios"))


# --- Bookmarks ---


@login_required
def bookmark_work(request, work_id):
    work = readable_work(request, work_id)
    if not services.can_interact(request.user):
        raise PermissionDenied
    existing = Bookmark.objects.filter(work=work, pseud__user=request.user).first()
    form = BookmarkForm(request.POST or None, instance=existing, user=request.user)
    if request.method == "POST" and form.is_valid():
        bookmark = form.save(commit=False)
        bookmark.work = work
        if Bookmark.objects.filter(work=work, pseud=bookmark.pseud).exclude(pk=bookmark.pk).exists():
            messages.error(request, _("Esse pseudônimo já salvou esta obra."))
        else:
            bookmark.save()
            form.save_tags(bookmark)
            queue_refresh([work.pk])
            messages.success(request, _("Bookmark salvo."))
            return redirect("works:detail", work_id=work.pk)
    return render(request, "interactions/bookmark_form.html", {"form": form, "work": work, "bookmark": existing})


@login_required
@require_POST
def delete_bookmark(request, bookmark_id):
    bookmark = get_object_or_404(Bookmark, pk=bookmark_id, pseud__user=request.user)
    work_id = bookmark.work_id
    bookmark.delete()
    queue_refresh([work_id])
    messages.success(request, _("Bookmark removido."))
    return redirect("interactions:user_bookmarks", username=request.user.username)


def bookmark_list(request, bookmarks, title, extra=None):
    visible_ids = base_listings(request.user).values("work_id")
    bookmarks = (
        bookmarks.filter(work_id__in=visible_ids)
        .select_related("pseud__user", "work__listing")
        .prefetch_related("tags")
        .order_by("-updated_at")
    )
    page = Paginator(bookmarks, 20).get_page(request.GET.get("pagina"))
    return render(request, "interactions/bookmark_list.html", {"page": page, "title": title, **(extra or {})})


def user_bookmarks(request, username):
    owner = get_object_or_404(get_user_model(), username=username)
    bookmarks = Bookmark.objects.filter(pseud__user=owner)
    if request.user != owner:
        bookmarks = bookmarks.filter(is_private=False)
    return bookmark_list(
        request, bookmarks, _("Bookmarks de %(name)s") % {"name": owner.username}, {"owner": owner}
    )


def work_bookmarks(request, work_id):
    work = readable_work(request, work_id)
    return bookmark_list(
        request,
        Bookmark.objects.filter(work=work, is_private=False),
        _("Bookmarks de “%(title)s”") % {"title": work.title},
    )
