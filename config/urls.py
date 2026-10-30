from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.flatpages.views import flatpage
from django.urls import include, path

from core import views as core_views

admin.site.site_header = settings.SITE_NAME
admin.site.site_title = settings.SITE_NAME

urlpatterns = [
    path("", core_views.home, name="home"),
    path("healthz/", core_views.healthz, name="healthz"),
    path("status/", core_views.status, name="status"),
    # Páginas de texto editáveis pelo admin (Páginas planas)
    path("sobre/", flatpage, {"url": "/sobre/"}, name="about"),
    path("termos/", flatpage, {"url": "/termos/"}, name="terms"),
    path("contato/", flatpage, {"url": "/contato/"}, name="contact"),
    path("idioma/", core_views.set_language, name="set_language"),
    path("", include("works.urls")),
    path("", include("tags.urls")),
    path("", include("interactions.urls")),
    path("", include("challenges.urls")),
    path("", include("messaging.urls")),
    path("", include("moderation.urls")),
    path("conta/", include("accounts.urls")),
    path("conta/", include("allauth.urls")),
    path(settings.ADMIN_URL, admin.site.urls),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
