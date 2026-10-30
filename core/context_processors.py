from django.conf import settings


def site(request):
    context = {
        "SITE_NAME": settings.SITE_NAME,
        "AVAILABLE_LANGUAGES": settings.LANGUAGES,
    }
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        from messaging.models import Conversation
        from moderation.models import Report
        from tags.wrangling import can_wrangle
        from works.models import WorkAuthor

        # Funções: só consultam o banco se o template usar
        context["CAN_WRANGLE"] = lambda: can_wrangle(user)
        context["PENDING_INVITES"] = lambda: WorkAuthor.objects.filter(
            pseud__user=user, status=WorkAuthor.Status.PENDING
        ).count()
        context["UNREAD_MESSAGES"] = lambda: Conversation.unread_for(user).count()
        if user.is_staff:
            context["OPEN_REPORTS"] = lambda: Report.objects.filter(status=Report.Status.OPEN).count()
    return context
