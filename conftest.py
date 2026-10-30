import pytest
from django.core.cache import cache

from config.celery import app as celery_app


@pytest.fixture(autouse=True)
def test_settings(settings):
    # Testes sem Redis, com hash de senha rápido e tarefas do Celery na hora
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    settings.LISTING_REFRESH_SYNC = True
    cache.clear()  # zera os limites de tentativas entre um teste e outro
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True


@pytest.fixture(autouse=True)
def fake_counters(monkeypatch):
    # Redis falso em memória para acessos e kudos
    import fakeredis

    from interactions import counters

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(counters, "_client", fake)
    return fake


@pytest.fixture
def make_user(django_user_model):
    def make(username="leitora", approved=True, **extra):
        return django_user_model.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="senha-bem-forte-123",
            is_approved=approved,
            **extra,
        )

    return make
