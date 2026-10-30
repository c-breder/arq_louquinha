import os
import shutil

from django.conf import settings
from django.db import connection


def _folder_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def collect():
    """Números de saúde do site (usados pelo comando status e pela página /status/)."""
    from accounts.models import User
    from interactions import counters
    from moderation.models import Report
    from tags.models import Tag
    from works.models import Chapter, Work

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_database_size(current_database())")
        db_bytes = cursor.fetchone()[0]
        cursor.execute(
            "SELECT relname, pg_total_relation_size(relid) FROM pg_catalog.pg_statio_user_tables "
            "ORDER BY 2 DESC LIMIT 5"
        )
        tables = cursor.fetchall()

    redis = counters.client()
    try:
        redis_memory = redis.info("memory").get("used_memory_human")
        pending_hits = sum(int(value) for value in redis.hvals(counters.PENDING_HITS))
        pending_kudos = redis.llen(counters.PENDING_KUDOS)
    except Exception:
        redis_memory, pending_hits, pending_kudos = "indisponível", None, None

    media_root = str(settings.MEDIA_ROOT)
    disk = shutil.disk_usage(media_root if os.path.exists(media_root) else "/")
    return {
        "database_mb": round(db_bytes / 1024 / 1024, 1),
        "largest_tables": [{"table": name, "mb": round(size / 1024 / 1024, 1)} for name, size in tables],
        "counts": {
            "users": User.objects.count(),
            "works": Work.objects.count(),
            "chapters": Chapter.objects.count(),
            "tags": Tag.objects.count(),
            "open_reports": Report.objects.filter(status=Report.Status.OPEN).count(),
        },
        "redis_memory": redis_memory,
        "pending": {"hits": pending_hits, "kudos": pending_kudos},
        "media_mb": round(_folder_size(media_root) / 1024 / 1024, 1),
        "disk": {
            "total_gb": round(disk.total / 1024**3, 1),
            "free_gb": round(disk.free / 1024**3, 1),
            "used_percent": round(100 * disk.used / disk.total, 1),
        },
    }
