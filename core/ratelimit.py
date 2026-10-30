import time

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import render


class RateLimitMiddleware:
    """Limite simples por IP e por minuto, guardado no Redis. Login tem limite próprio no allauth."""

    SKIP_PREFIXES = ("/static/", "/media/", "/healthz/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.RATE_LIMIT_ENABLED and not request.path.startswith(self.SKIP_PREFIXES):
            for bucket, limit in self.buckets(request.path):
                if self.hit(bucket, request.META.get("REMOTE_ADDR", ""), limit):
                    response = render(request, "429.html", status=429)
                    response["Retry-After"] = "60"
                    return response
        return self.get_response(request)

    def buckets(self, path):
        yield "global", settings.RATE_LIMIT_GLOBAL
        if path == "/obras/" or path == "/tags/":
            yield "search", settings.RATE_LIMIT_SEARCH
        elif path.startswith("/tags/autocompletar/"):
            yield "autocomplete", settings.RATE_LIMIT_AUTOCOMPLETE

    def hit(self, bucket, ip, limit):
        key = f"rl:{bucket}:{ip}:{int(time.time() // 60)}"
        cache.add(key, 0, timeout=70)
        try:
            return cache.incr(key) > limit
        except ValueError:
            return False
