from uuid import uuid4

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Sum
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from core.images import process_image
from tags.models import Tag

from . import services
from .forms import ChapterForm, CoauthorInviteForm, PublishForm, WorkForm, publish_actions
from .listing import base_listings, queue_refresh
from .models import Chapter, PublicationStatus, Work, WorkAuthor, WorkImage, WorkListing
from .search import WorkSearchForm, search
from .series import AddToSeriesForm, series_nav
from .sanitize import clean_html

ADULT_RATINGS = {Work.Rating.MATURE, Work.Rating.EXPLICIT}
SAVE_ONLY = [("draft", gettext_lazy("Salvar"))]


def editor_context(user, work=None):
    can_upload = user.can_upload_images
    return {
        "upload_url": reverse("works:image_upload") if can_upload else "",
        "labels": {
            "visual": _("Texto formatado"),
            "html": _("HTML"),
            "bold": _("Negrito"),
            "italic": _("Itálico"),
            "underline": _("Sublinhado"),
            "strike": _("Riscado"),
            "heading": _("Título"),
            "paragraph": _("Parágrafo"),
            "quote": _("Citação"),
            "bullets": _("Lista"),
            "numbers": _("Lista numerada"),
            "link": _("Link"),
            "link_prompt": _("Endereço do link (https://...)"),
            "rule": _("Linha divisória"),
            "image": _("Imagem"),
            "image_alt": _("Descreva a imagem para quem não pode vê-la:"),
            "uploading": _("Enviando imagem..."),
            "upload_error": _("Não foi possível enviar a imagem."),
        },
    }


def status_message(obj):
    if obj.status == PublicationStatus.PUBLISHED:
        return _("Publicado.")
    if obj.status == PublicationStatus.SCHEDULED:
        when = date_format(timezone.localtime(obj.scheduled_for), "DATETIME_FORMAT")
        return _("Agendado para %(when)s.") % {"when": when}
    return _("Rascunho salvo.")


def get_editable_work(request, work_id):
    work = get_object_or_404(Work, pk=work_id)
    if not services.user_can_edit(request.user, work):
        raise PermissionDenied
    return work


def get_readable_work(request, work_id):
    work = get_object_or_404(Work, pk=work_id)
    can_edit = services.user_can_edit(request.user, work)
    privileged = can_edit or request.user.is_staff
    if (work.status != PublicationStatus.PUBLISHED or work.hidden_by_moderator) and not privileged:
        raise Http404
    return work, privileged, can_edit


def reading_gate(request, work):
    # Obra só para logados e aviso de conteúdo adulto para visitantes
    if work.restricted and not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path())
    if work.rating in ADULT_RATINGS and not request.user.is_authenticated:
        accepted = request.session.get("adult_works", [])
        if request.GET.get("adulto") == "1":
            if work.pk not in accepted:
                request.session["adult_works"] = (accepted + [work.pk])[-200:]
        elif work.pk not in accepted:
            return render(request, "works/adult_warning.html", {"work": work})
    return None


# --- Leitura ---


def work_detail(request, work_id, position=None, full=False):
    work, privileged, can_edit = get_readable_work(request, work_id)
    blocked = reading_gate(request, work)
    if blocked:
        return blocked

    chapters = work.chapters.order_by("position")
    if not privileged:
        chapters = chapters.filter(status=PublicationStatus.PUBLISHED)
    chapters = list(chapters)
    if not chapters:
        raise Http404

    if full:
        shown = chapters
    elif position is None:
        shown = chapters[:1]
    else:
        shown = [chapter for chapter in chapters if chapter.position == position]
        if not shown:
            raise Http404

    index = chapters.index(shown[0])
    show_images = services.images_visible(work)
    tags = list(work.tags.all())
    published_count = sum(1 for chapter in chapters if chapter.status == PublicationStatus.PUBLISHED)
    context = {
        "work": work,
        "can_edit": can_edit,
        "authors": list(work.authors),
        "chapters": chapters,
        "rendered": [(chapter, clean_html(chapter.content, allow_images=show_images)) for chapter in shown],
        "current": shown[0],
        "full": full,
        "previous": chapters[index - 1] if not full and index > 0 else None,
        "next": chapters[index + 1] if not full and index + 1 < len(chapters) else None,
        "tag_groups": [
            (label, [tag for tag in tags if tag.type == value]) for value, label in Tag.Type.choices
        ],
        "warning_labels": [Work.Warning(value).label for value in work.warnings],
        "category_labels": [Work.Category(value).label for value in work.categories],
        "hide_warnings": request.user.is_authenticated and request.user.hide_warnings,
        "published_count": published_count,
    }
    if work.status == PublicationStatus.PUBLISHED and not work.hidden_by_moderator:
        context.update(reader_context(request, work, shown[0], full))
    return render(request, "works/work_detail.html", context)


def reader_context(request, work, chapter, full):
    """Kudos, acessos, comentários, série e coleções: só em obras publicadas."""
    from challenges.models import CollectionItem
    from interactions import services as interactions
    from interactions.forms import CommentForm
    from interactions.models import Bookmark

    interactions.register_hit(request, work)
    user = request.user
    can_interact = interactions.can_interact(user)
    return {
        "is_public": True,
        "kudos": interactions.kudos_summary(work),
        "hits": interactions.total_hits(work),
        "bookmark_count": Bookmark.objects.filter(work=work, is_private=False).count(),
        "my_bookmark": Bookmark.objects.filter(work=work, pseud__user=user).first() if user.is_authenticated else None,
        "series_nav": series_nav(work, user),
        "collections": [
            item.collection
            for item in CollectionItem.objects.filter(work=work, status=CollectionItem.Status.APPROVED).select_related(
                "collection"
            )
        ],
        "comment_chapter": None if full else chapter,
        "comments": [] if full or chapter.status != PublicationStatus.PUBLISHED else interactions.comment_tree(chapter, user),
        "comment_form": CommentForm(user=user) if can_interact else None,
        "can_interact": can_interact,
    }


def chapter_detail(request, work_id, position):
    return work_detail(request, work_id, position=position)


def work_full(request, work_id):
    return work_detail(request, work_id, full=True)


# --- Criar e editar ---


@login_required
def work_create(request):
    user = request.user
    form = WorkForm(request.POST or None, user=user)
    chapter_form = ChapterForm(request.POST or None, prefix="chapter", allow_images=user.can_upload_images)
    publish_form = PublishForm(request.POST or None)
    if request.method == "POST" and all([form.is_valid(), chapter_form.is_valid(), publish_form.is_valid()]):
        work = services.save_work(
            form,
            user,
            chapter_form,
            publish_form.cleaned_data["action"],
            publish_form.cleaned_data.get("scheduled_for"),
        )
        messages.success(request, status_message(work))
        return redirect("works:detail", work_id=work.pk)
    return render(
        request,
        "works/work_form.html",
        {
            "form": form,
            "chapter_form": chapter_form,
            "publish_form": publish_form,
            "actions": PublishForm.ACTIONS,
            "editor": editor_context(user),
        },
    )


@login_required
def work_edit(request, work_id):
    work = get_editable_work(request, work_id)
    form = WorkForm(request.POST or None, instance=work, user=request.user)
    publish_form = PublishForm(request.POST or None)
    if request.method == "POST" and form.is_valid() and publish_form.is_valid():
        services.save_work(
            form,
            request.user,
            action=publish_form.cleaned_data["action"],
            scheduled_for=publish_form.cleaned_data.get("scheduled_for"),
        )
        work.refresh_from_db()
        messages.success(request, status_message(work))
        return redirect("works:detail", work_id=work.pk)
    return render(
        request,
        "works/work_form.html",
        {
            "work": work,
            "form": form,
            "publish_form": publish_form,
            "actions": publish_actions(work) or SAVE_ONLY,
            "invite_form": CoauthorInviteForm(work=work),
            "authorships": work.authorships.select_related("pseud__user").order_by("created_at"),
            "series_form": AddToSeriesForm(user=request.user),
            "series_entries": work.series_entries.select_related("series"),
            "collection_items": work.collection_items.select_related("collection"),
            "editor": editor_context(request.user, work),
        },
    )


@login_required
def work_delete(request, work_id):
    work = get_editable_work(request, work_id)
    if request.method == "POST":
        services.delete_work(work)
        messages.success(request, _("Obra excluída."))
        return redirect("works:my_works")
    return render(request, "works/confirm_delete.html", {"work": work})


def chapter_allows_images(user, work):
    # Coautor sem nível de imagens não apaga as imagens já colocadas por quem tem
    return user.can_upload_images or services.images_visible(work)


@login_required
def chapter_create(request, work_id):
    work = get_editable_work(request, work_id)
    form = ChapterForm(request.POST or None, allow_images=chapter_allows_images(request.user, work))
    publish_form = PublishForm(request.POST or None)
    if request.method == "POST" and all([form.is_valid(), publish_form.is_valid()]):
        chapter = services.save_chapter(
            form, work, publish_form.cleaned_data["action"], publish_form.cleaned_data.get("scheduled_for")
        )
        messages.success(request, status_message(chapter))
        return redirect("works:chapter", work_id=work.pk, position=chapter.position)
    return render(
        request,
        "works/chapter_form.html",
        {
            "work": work,
            "form": form,
            "publish_form": publish_form,
            "actions": PublishForm.ACTIONS,
            "editor": editor_context(request.user, work),
        },
    )


@login_required
def chapter_edit(request, work_id, position):
    work = get_editable_work(request, work_id)
    chapter = get_object_or_404(Chapter, work=work, position=position)
    form = ChapterForm(request.POST or None, instance=chapter, allow_images=chapter_allows_images(request.user, work))
    publish_form = PublishForm(request.POST or None)
    if request.method == "POST" and all([form.is_valid(), publish_form.is_valid()]):
        chapter = services.save_chapter(
            form, work, publish_form.cleaned_data["action"], publish_form.cleaned_data.get("scheduled_for")
        )
        messages.success(request, status_message(chapter))
        return redirect("works:chapter", work_id=work.pk, position=chapter.position)
    return render(
        request,
        "works/chapter_form.html",
        {
            "work": work,
            "chapter": chapter,
            "form": form,
            "publish_form": publish_form,
            "actions": publish_actions(chapter) or SAVE_ONLY,
            "editor": editor_context(request.user, work),
        },
    )


@login_required
def chapter_delete(request, work_id, position):
    work = get_editable_work(request, work_id)
    chapter = get_object_or_404(Chapter, work=work, position=position)
    if work.chapters.count() == 1:
        messages.error(request, _("Uma obra precisa de pelo menos um capítulo. Para apagar tudo, exclua a obra."))
        return redirect("works:edit", work_id=work.pk)
    if request.method == "POST":
        services.delete_chapter(chapter)
        messages.success(request, _("Capítulo excluído."))
        return redirect("works:detail", work_id=work.pk)
    return render(request, "works/confirm_delete.html", {"work": work, "chapter": chapter})


# --- Coautoria ---


@login_required
@require_POST
def coauthor_invite(request, work_id):
    work = get_editable_work(request, work_id)
    form = CoauthorInviteForm(request.POST, work=work)
    if form.is_valid():
        services.invite_coauthor(work, form.pseud, request.user)
        messages.success(request, _("Convite enviado."))
    else:
        for error in form.errors.get("username", []):
            messages.error(request, error)
    return redirect("works:edit", work_id=work.pk)


@login_required
@require_POST
def leave_work(request, work_id):
    work = get_editable_work(request, work_id)
    if services.leave_work(work, request.user):
        messages.success(request, _("Você saiu da autoria desta obra."))
        return redirect("works:my_works")
    messages.error(request, _("Você é o único autor. Para sair, exclua a obra."))
    return redirect("works:edit", work_id=work.pk)


@login_required
def invitations(request):
    pending = (
        WorkAuthor.objects.filter(pseud__user=request.user, status=WorkAuthor.Status.PENDING)
        .select_related("work", "pseud", "invited_by")
        .order_by("-created_at")
    )
    return render(request, "works/invitations.html", {"invitations": pending})


@login_required
@require_POST
def respond_invitation(request, authorship_id):
    authorship = get_object_or_404(
        WorkAuthor, pk=authorship_id, pseud__user=request.user, status=WorkAuthor.Status.PENDING
    )
    if request.POST.get("decision") == "accept":
        authorship.status = WorkAuthor.Status.ACCEPTED
        authorship.save(update_fields=["status"])
        queue_refresh([authorship.work_id])
        messages.success(request, _("Agora você é coautor(a) de \"%(title)s\".") % {"title": authorship.work.title})
    else:
        authorship.delete()
        messages.info(request, _("Convite recusado."))
    return redirect("works:invitations")


# --- Listas ---


@login_required
def my_works(request):
    works = (
        Work.objects.filter(authorships__pseud__user=request.user, authorships__status=WorkAuthor.Status.ACCEPTED)
        .distinct()
        .order_by("-updated_at")
    )
    page = Paginator(works, 20).get_page(request.GET.get("pagina"))
    return render(request, "works/my_works.html", {"page": page})


def search_works(request):
    form = WorkSearchForm(request.GET)
    results = search(request.user, form) if form.is_valid() else WorkListing.objects.none()
    page = Paginator(results, 20).get_page(request.GET.get("pagina"))
    query_string = request.GET.copy()
    query_string.pop("pagina", None)
    return render(
        request,
        "works/search.html",
        {"form": form, "page": page, "query_string": query_string.urlencode()},
    )


def user_profile(request, username):
    profile = get_object_or_404(get_user_model(), username=username)
    work_ids = WorkAuthor.objects.filter(pseud__user=profile, status=WorkAuthor.Status.ACCEPTED).values("work_id")
    listings = base_listings(request.user).filter(work_id__in=work_ids).order_by("-revised_at")
    page = Paginator(listings, 20).get_page(request.GET.get("pagina"))
    return render(
        request,
        "works/user_profile.html",
        {"profile": profile, "pseuds": profile.pseuds.all(), "page": page},
    )


# --- Imagens no texto ---


@login_required
@require_POST
def image_upload(request):
    user = request.user
    if not user.can_upload_images:
        return JsonResponse({"error": _("Seu nível de mídia não permite imagens no texto.")}, status=403)
    upload = request.FILES.get("image")
    if upload is None:
        return JsonResponse({"error": _("Nenhum arquivo enviado.")}, status=400)
    if upload.size > settings.MAX_IMAGE_UPLOAD_MB * 1024 * 1024:
        return JsonResponse(
            {"error": _("A imagem passa de %(max)d MB.") % {"max": settings.MAX_IMAGE_UPLOAD_MB}}, status=400
        )
    try:
        content, width, height = process_image(upload, max_width=settings.IMAGE_MAX_WIDTH)
    except ValidationError as error:
        return JsonResponse({"error": error.messages[0]}, status=400)
    used = WorkImage.objects.filter(owner=user).aggregate(total=Sum("size"))["total"] or 0
    if used + content.size > settings.IMAGE_QUOTA_MB * 1024 * 1024:
        return JsonResponse({"error": _("Você atingiu o limite de espaço para imagens.")}, status=400)
    image = WorkImage(owner=user, size=content.size, width=width, height=height)
    image.file.save(f"{uuid4().hex}.webp", content, save=True)
    return JsonResponse({"url": image.file.url, "width": image.width, "height": image.height})
