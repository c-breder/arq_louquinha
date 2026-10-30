from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from works.listing import base_listings, tag_filter_id

from . import wrangling
from .models import Tag
from .wrangling import WranglingError, can_wrangle


def wrangler_required(view):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not can_wrangle(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def safe_next(request, fallback):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return target
    return fallback


# --- Páginas públicas ---


def tag_detail(request, tag_id):
    tag = get_object_or_404(Tag.objects.select_related("merger"), pk=tag_id)
    # Mesma regra da Fase 3 (canônica + sinônimos + subtags), lida da tabela de listagens
    listings = base_listings(request.user).filter(filter_ids__contains=[tag_filter_id(tag)]).order_by("-revised_at")
    page = Paginator(listings, 20).get_page(request.GET.get("pagina"))
    children = []
    if tag.type == Tag.Type.FANDOM and tag.canonical:
        linked = list(tag.fandom_children.filter(canonical=True).order_by("-use_count", "name")[:60])
        children = [
            (label, [child for child in linked if child.type == value])
            for value, label in Tag.Type.choices
            if value != Tag.Type.FANDOM
        ]
    return render(
        request,
        "tags/tag_detail.html",
        {
            "tag": tag,
            "page": page,
            "synonyms": tag.synonyms.order_by("name"),
            "metatags": Tag.objects.filter(sub_taggings__sub=tag).order_by("name"),
            "subtags": Tag.objects.filter(meta_taggings__meta=tag).order_by("name"),
            "fandoms": tag.fandoms.order_by("name"),
            "children": children,
            "can_wrangle": can_wrangle(request.user),
        },
    )


def tag_search(request):
    query = request.GET.get("q", "").strip()
    tag_type = request.GET.get("tipo", "")
    only_canonical = request.GET.get("canonicas", "1") == "1"
    tags = Tag.objects.all()
    if query:
        tags = tags.filter(name__icontains=query)
    if tag_type in Tag.Type.values:
        tags = tags.filter(type=tag_type)
    if only_canonical:
        tags = tags.filter(canonical=True)
    page = Paginator(tags.order_by("-use_count", "name"), 50).get_page(request.GET.get("pagina"))
    return render(
        request,
        "tags/tag_search.html",
        {"page": page, "query": query, "tag_type": tag_type, "only_canonical": only_canonical, "types": Tag.Type.choices},
    )


def fandom_index(request):
    fandoms = Tag.objects.filter(type=Tag.Type.FANDOM, canonical=True).order_by("name")
    return render(request, "tags/fandoms.html", {"fandoms": fandoms})


def autocomplete(request):
    # Sugere só canônicas; digitar um sinônimo sugere a canônica dele
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})
    tags = Tag.objects.filter(name__icontains=query)
    tag_type = request.GET.get("tipo")
    if tag_type in Tag.Type.values:
        tags = tags.filter(type=tag_type)
    names = list(tags.filter(canonical=True).order_by("-use_count", "name").values_list("name", flat=True)[:10])
    for name in tags.filter(merger__isnull=False).order_by("-use_count").values_list("merger__name", flat=True)[:10]:
        if name not in names and len(names) < 10:
            names.append(name)
    return JsonResponse({"results": names})


# --- Wrangling ---

STATUSES = [
    ("pendentes", gettext_lazy("Sem decisão")),
    ("sem_fandom", gettext_lazy("Canônicas sem fandom")),
    ("canonicas", gettext_lazy("Canônicas")),
    ("sinonimos", gettext_lazy("Sinônimos")),
]


@wrangler_required
def wrangling_home(request):
    tag_type = request.GET.get("tipo")
    if tag_type not in Tag.Type.values:
        tag_type = Tag.Type.FREEFORM
    status = request.GET.get("situacao", "pendentes")
    query = request.GET.get("q", "").strip()

    tags = Tag.objects.filter(type=tag_type).select_related("merger")
    if status == "sem_fandom":
        tags = tags.filter(canonical=True, fandoms__isnull=True).exclude(type=Tag.Type.FANDOM)
    elif status == "canonicas":
        tags = tags.filter(canonical=True)
    elif status == "sinonimos":
        tags = tags.filter(merger__isnull=False)
    else:
        status = "pendentes"
        tags = tags.filter(canonical=False, merger__isnull=True)
    if query:
        tags = tags.filter(name__icontains=query)

    pending = dict(
        Tag.objects.filter(canonical=False, merger__isnull=True).values_list("type").annotate(total=Count("pk"))
    )
    page = Paginator(tags.order_by("-use_count", "name"), 50).get_page(request.GET.get("pagina"))
    return render(
        request,
        "tags/wrangling_home.html",
        {
            "page": page,
            "tag_type": tag_type,
            "status": status,
            "query": query,
            "type_tabs": [(value, label, pending.get(value, 0)) for value, label in Tag.Type.choices],
            "statuses": STATUSES,
        },
    )


@wrangler_required
@require_POST
def wrangling_bulk(request):
    back = safe_next(request, "/wrangling/")
    tags = list(Tag.objects.filter(pk__in=request.POST.getlist("tag_ids")))
    operation = request.POST.get("op")
    target_name = request.POST.get("target", "").strip()
    if not tags:
        messages.error(request, _("Selecione pelo menos uma tag."))
        return redirect(back)
    done = 0
    for tag in tags:
        try:
            if operation == "canonize":
                done += wrangling.canonize(tag, request.user)
            elif operation == "merge":
                done += wrangling.make_synonym(tag, wrangling.find_canonical(target_name, tag.type), request.user)
            elif operation == "fandom":
                fandom = wrangling.find_canonical(request.POST.get("fandom_target", ""), Tag.Type.FANDOM)
                done += wrangling.add_fandom(tag, fandom, request.user)
        except WranglingError as error:
            messages.error(request, f"{tag.name}: {error}")
    if done:
        messages.success(request, _("%(count)d tag(s) atualizada(s).") % {"count": done})
    return redirect(back)


@wrangler_required
def wrangle_tag(request, tag_id):
    tag = get_object_or_404(Tag.objects.select_related("merger"), pk=tag_id)
    if request.method == "POST":
        operation = request.POST.get("op")
        target = request.POST.get("target", "")
        actor = request.user
        try:
            if operation == "canonize":
                wrangling.canonize(tag, actor)
            elif operation == "decanonize":
                wrangling.decanonize(tag, actor)
            elif operation == "merge":
                wrangling.make_synonym(tag, wrangling.find_canonical(target, tag.type), actor)
            elif operation == "unmerge":
                wrangling.unmerge(tag, actor)
            elif operation == "add_meta":
                wrangling.add_metatag(tag, wrangling.find_canonical(target, tag.type), actor)
            elif operation == "remove_meta":
                wrangling.remove_metatag(tag, get_object_or_404(Tag, pk=request.POST.get("other")), actor)
            elif operation == "add_sub":
                wrangling.add_metatag(wrangling.find_canonical(target, tag.type), tag, actor)
            elif operation == "remove_sub":
                wrangling.remove_metatag(get_object_or_404(Tag, pk=request.POST.get("other")), tag, actor)
            elif operation == "add_fandom":
                wrangling.add_fandom(tag, wrangling.find_canonical(target, Tag.Type.FANDOM), actor)
            elif operation == "remove_fandom":
                wrangling.remove_fandom(tag, get_object_or_404(Tag, pk=request.POST.get("other")), actor)
            messages.success(request, _("Tag atualizada."))
        except WranglingError as error:
            messages.error(request, str(error))
        return redirect("tags:wrangle", tag_id=tag.pk)
    return render(
        request,
        "tags/wrangle_tag.html",
        {
            "tag": tag,
            "synonyms": tag.synonyms.order_by("name"),
            "metatags": Tag.objects.filter(sub_taggings__sub=tag).order_by("name"),
            "subtags": Tag.objects.filter(meta_taggings__meta=tag).order_by("name"),
            "fandoms": tag.fandoms.order_by("name"),
            "is_fandom": tag.type == Tag.Type.FANDOM,
        },
    )
