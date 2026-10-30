"""Acessos e kudos ficam no Redis e o worker grava no banco em lote (menos escrita no Postgres)."""

import json
import time

import redis
from django.conf import settings

PENDING_HITS = "hits:pending"
PENDING_KUDOS = "kudos:pending"
PENDING_KUDOS_COUNT = "kudos:pending:count"
SEEN_HIT_SECONDS = 24 * 60 * 60

_client = None


def client():
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.COUNTERS_REDIS_URL, decode_responses=True)
    return _client


# --- Acessos ---


def register_hit(work_id, visitor):
    # Conta no máximo 1 acesso por visitante por obra a cada 24 h
    r = client()
    if r.set(f"hits:seen:{work_id}:{visitor}", 1, nx=True, ex=SEEN_HIT_SECONDS):
        r.hincrby(PENDING_HITS, work_id, 1)
        return True
    return False


def pending_hits(work_id):
    return int(client().hget(PENDING_HITS, work_id) or 0)


def take_pending_hits():
    r = client()
    flushing = f"{PENDING_HITS}:flushing"
    try:
        r.rename(PENDING_HITS, flushing)
    except redis.ResponseError:
        return {}  # nada pendente
    data = r.hgetall(flushing)
    r.delete(flushing)
    return {int(work_id): int(total) for work_id, total in data.items()}


# --- Kudos ---


def queue_kudos(work_id, user_id=None, guest_key=""):
    """False se essa pessoa já deixou kudos e ainda está na fila."""
    r = client()
    seen = f"kudos:seen:{work_id}"
    if not r.sadd(seen, f"u:{user_id}" if user_id else f"g:{guest_key}"):
        return False
    r.expire(seen, 2 * 60 * 60)
    r.rpush(PENDING_KUDOS, json.dumps({"work": work_id, "user": user_id, "guest": guest_key, "at": time.time()}))
    r.hincrby(PENDING_KUDOS_COUNT, work_id, 1)
    return True


def kudos_in_queue(work_id, user_id=None, guest_key=""):
    return client().sismember(f"kudos:seen:{work_id}", f"u:{user_id}" if user_id else f"g:{guest_key}")


def pending_kudos(work_id):
    return int(client().hget(PENDING_KUDOS_COUNT, work_id) or 0)


def take_pending_kudos(batch=1000):
    r = client()
    items = []
    while True:
        chunk = r.lpop(PENDING_KUDOS, batch)
        if not chunk:
            return items
        items.extend(json.loads(item) for item in chunk)


def settle_kudos_counts(totals):
    # Depois de gravar no banco, tira da contagem pendente
    r = client()
    for work_id, total in totals.items():
        if r.hincrby(PENDING_KUDOS_COUNT, work_id, -total) <= 0:
            r.hdel(PENDING_KUDOS_COUNT, work_id)
