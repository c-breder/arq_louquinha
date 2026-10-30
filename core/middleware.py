from django.conf import settings
from django.shortcuts import redirect
from django.utils import translation

from .languages import get_request_language


class CloudflareRealIPMiddleware:
    # Só confia no CF-Connecting-IP quando o site está atrás do túnel
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.TRUST_CF_CONNECTING_IP:
            real_ip = request.META.get("HTTP_CF_CONNECTING_IP")
            if real_ip:
                request.META["REMOTE_ADDR"] = real_ip
        return self.get_response(request)


class UserLanguageMiddleware:
    # Substitui o LocaleMiddleware do Django, que usaria o idioma do navegador
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = get_request_language(request)
        translation.activate(language)
        request.LANGUAGE_CODE = language
        response = self.get_response(request)
        response.headers.setdefault("Content-Language", language)
        return response


class ApprovalRequiredMiddleware:
    # Conta aguardando aprovação só acessa as páginas da própria conta
    ALLOWED_PREFIXES = ("/conta/", "/idioma/", "/healthz/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if (
            user.is_authenticated
            and not user.is_approved
            and not user.is_staff
            and not self._is_allowed(request.path)
        ):
            return redirect("accounts:pending_approval")
        return self.get_response(request)

    def _is_allowed(self, path):
        prefixes = self.ALLOWED_PREFIXES + (settings.STATIC_URL, settings.MEDIA_URL)
        return path.startswith(prefixes)
