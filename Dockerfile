FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# gettext: necessário para compilar as traduções (compilemessages)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY requirements/ requirements/
RUN pip install -r requirements/base.txt


FROM base AS dev
RUN pip install -r requirements/dev.txt
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


FROM base AS prod
COPY --chown=app:app . .
# Valores falsos só para o build; os reais vêm do .env
RUN export DJANGO_SECRET_KEY=build-only POSTGRES_PASSWORD=build-only \
    && python manage.py collectstatic --noinput \
    && python manage.py compilemessages \
    && mkdir -p /app/media && chown app:app /app/media
USER app
CMD gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers ${GUNICORN_WORKERS:-2} \
    --worker-class gthread --threads ${GUNICORN_THREADS:-2} \
    --timeout 30 \
    --max-requests 1000 --max-requests-jitter 100 \
    --access-logfile -


# Caddy com os estáticos já embutidos (mesma versão do código)
FROM caddy:2-alpine AS caddy
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=prod /app/staticfiles /srv/static


# Backup: ferramentas do Postgres + rclone para cópia fora da máquina
FROM postgres:17-alpine AS backup
RUN apk add --no-cache rclone tzdata
COPY deploy/backup/ /scripts/
RUN chmod +x /scripts/*.sh
CMD ["/scripts/loop.sh"]
