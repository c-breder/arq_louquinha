from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from interactions.services import can_interact
from works.listing import base_listings
from works.models import Work
from works.services import user_can_edit

from .forms import AddWorkForm, CollectionForm, PromptForm
from .models import Collection, CollectionItem, Prompt


def collection_index(request):
    collections = Collection.objects.annotate(
        works=Count("items", filter=Q(items__status=CollectionItem.Status.APPROVED))
    ).order_by("-is_open", "title")
    return render(request, "challenges/index.html", {"collections": collections})


def approved_listings(request, collection):
    work_ids = collection.items.filter(status=CollectionItem.Status.APPROVED).values("work_id")
    return base_listings(request.user).filter(work_id__in=work_ids)


def collection_detail(request, slug):
    collection = get_object_or_404(Collection, slug=slug)
    listings = approved_listings(request, collection).order_by("-revised_at")
    page = Paginator(listings, 20).get_page(request.GET.get("pagina"))
    prompts = collection.prompts.annotate(
        fill_count=Count("fills", filter=Q(fills__status=CollectionItem.Status.APPROVED))
    )
    return render(
        request,
        "challenges/detail.html",
        {
            "collection": collection,
            "page": page,
            "prompts": prompts if collection.kind == Collection.Kind.PROMPT_MEME else None,
            "prompt_form": PromptForm(),
            "can_manage": collection.can_manage(request.user),
            "pending": collection.items.filter(status=CollectionItem.Status.PENDING).count(),
        },
    )


@login_required
def collection_form(request, slug=None):
    collection = get_object_or_404(Collection, slug=slug) if slug else None
    if collection and not collection.can_manage(request.user):
        raise PermissionDenied
    if not collection and not can_interact(request.user):
        raise PermissionDenied
    form = CollectionForm(request.POST or None, instance=collection)
    if request.method == "POST" and form.is_valid():
        saved = form.save(commit=False)
        if not collection:
            saved.owner = request.user
        saved.save()
        messages.success(request, _("Coleção salva."))
        return redirect("challenges:detail", slug=saved.slug)
    return render(request, "challenges/form.html", {"form": form, "collection": collection})


@login_required
def collection_manage(request, slug):
    collection = get_object_or_404(Collection, slug=slug)
    if not collection.can_manage(request.user):
        raise PermissionDenied
    if request.method == "POST":
        item = get_object_or_404(CollectionItem, pk=request.POST.get("item"), collection=collection)
        decision = request.POST.get("decision")
        if decision in (CollectionItem.Status.APPROVED, CollectionItem.Status.REJECTED):
            item.status = decision
            item.save(update_fields=["status"])
            messages.success(request, _("Decisão registrada."))
        return redirect("challenges:manage", slug=slug)
    items = collection.items.select_related("work", "prompt", "added_by").order_by("status", "-created_at")
    return render(request, "challenges/manage.html", {"collection": collection, "items": items})


@login_required
@require_POST
def add_prompt(request, slug):
    collection = get_object_or_404(Collection, slug=slug, kind=Collection.Kind.PROMPT_MEME)
    if not can_interact(request.user) or not collection.accepting:
        raise PermissionDenied
    form = PromptForm(request.POST)
    if form.is_valid():
        Prompt.objects.create(collection=collection, author=request.user, text=form.cleaned_data["text"])
        messages.success(request, _("Prompt enviado."))
    return redirect("challenges:detail", slug=slug)


@login_required
@require_POST
def add_work(request, work_id):
    work = get_object_or_404(Work, pk=work_id)
    if not user_can_edit(request.user, work):
        raise PermissionDenied
    form = AddWorkForm(request.POST)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("works:edit", work_id=work.pk)
    collection = form.cleaned_data["collection"]
    prompt = None
    if form.cleaned_data.get("prompt"):
        prompt = collection.prompts.filter(pk=form.cleaned_data["prompt"]).first()
    # Coleção moderada: dono aprova. O dono da coleção não precisa aprovar a própria obra.
    status = CollectionItem.Status.APPROVED
    if collection.is_moderated and not collection.can_manage(request.user):
        status = CollectionItem.Status.PENDING
    item, created = CollectionItem.objects.get_or_create(
        collection=collection, work=work, defaults={"status": status, "prompt": prompt, "added_by": request.user}
    )
    if not created:
        messages.info(request, _("A obra já está nessa coleção."))
    elif item.status == CollectionItem.Status.PENDING:
        messages.success(request, _("Obra enviada. Ela aparece depois que a moderação da coleção aprovar."))
    else:
        messages.success(request, _("Obra adicionada à coleção “%(title)s”.") % {"title": collection.title})
    return redirect("works:edit", work_id=work.pk)


@login_required
@require_POST
def remove_work(request, work_id, slug):
    item = get_object_or_404(CollectionItem, work_id=work_id, collection__slug=slug)
    if not (user_can_edit(request.user, item.work) or item.collection.can_manage(request.user)):
        raise PermissionDenied
    item.delete()
    messages.success(request, _("Obra removida da coleção."))
    return redirect(request.POST.get("next") or "works:my_works")
