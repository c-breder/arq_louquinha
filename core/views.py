from datetime import timedelta

from django.db import connection
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .languages import set_language_cookie, supported_languages

FEATURED_COUNT = 6
FEATURED_DAYS = 90
RECENT_UPDATES = 6


def home(request):
    from works.listing import base_listings
    from works.models import Chapter, PublicationStatus

    listings = base_listings(request.user)
    # Destaque: mais kudos entre as atualizadas recentemente; completa com as mais queridas de todas
    recent_cutoff = timezone.now() - timedelta(days=FEATURED_DAYS)
    featured = list(listings.filter(revised_at__gte=recent_cutoff).order_by("-kudos_count", "-revised_at")[:FEATURED_COUNT])
    if len(featured) < FEATURED_COUNT:
        chosen = [listing.work_id for listing in featured]
        featured += list(
            listings.exclude(work_id__in=chosen).order_by("-kudos_count", "-revised_at")[: FEATURED_COUNT - len(featured)]
        )

    updates = (
        Chapter.objects.filter(status=PublicationStatus.PUBLISHED, work_id__in=listings.values("work_id"))
        .select_related("work__listing")
        .order_by("-published_at")[:RECENT_UPDATES]
    )
    return render(request, "core/home.html", {"featured": featured, "updates": updates})


def healthz(request):
    connection.ensure_connection()
    return JsonResponse({"status": "ok"})


def status(request):
    # Detalhes só para a equipe; o público tem o /healthz/
    if not request.user.is_staff:
        raise Http404
    from .status import collect

    return JsonResponse(collect(), json_dumps_params={"ensure_ascii": False, "indent": 2})


@require_POST
def set_language(request):
    language = request.POST.get("language")
    next_url = request.POST.get("next") or "/"
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = "/"
    response = redirect(next_url)
    if language in supported_languages():
        if request.user.is_authenticated:
            request.user.language = language
            request.user.save(update_fields=["language"])
        set_language_cookie(response, language)
    return response
