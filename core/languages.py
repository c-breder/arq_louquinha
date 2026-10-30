from django.conf import settings


def supported_languages():
    return {code for code, _name in settings.LANGUAGES}


def get_request_language(request):
    # Ordem: preferência da conta > cookie > português. Nunca usa o idioma do navegador.
    supported = supported_languages()
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.language in supported:
        return user.language
    cookie = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
    if cookie in supported:
        return cookie
    return settings.LANGUAGE_CODE


def set_language_cookie(response, language):
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        language,
        max_age=settings.LANGUAGE_COOKIE_AGE,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE,
        secure=settings.LANGUAGE_COOKIE_SECURE,
        httponly=True,
    )
